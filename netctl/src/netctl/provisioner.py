"""GnmiProvisioner — the real hands: M2.2's recipe as code (docs/07 §6.1).

Satisfies the `NetworkProvisioner` Protocol (docs/03 §5), same hole as
`MockProvisioner` (rule 7 — one shared contract suite runs against both). Topology-
agnostic by rule 6/ADR-005: it receives concrete device + interface names inside
`ResolvedPath` and a device→target map at construction; it knows nothing about
tickets, chains, or resource ids.

Sessions leave a NAME on the router, not state in this process: every policer
template is called `a2a-<session_id>`, so `teardown` can always find its own work
by reading the router — surviving restarts, and making "tear down twice" naturally
a success (rule 8).
"""

from __future__ import annotations

from a2a_interfaces import ApplyResult, ResolvedNode, ResolvedPath

from . import paths
from .connect import GnmiTarget, connect

# 20 ms of burst at 50 Mbps ≈ 125 KB — the M2.2 lab value; enough for TCP to breathe,
# small enough that the plateau stays crisp.
_BURST_BYTES = 125_000


def _template_name(session_id: str) -> str:
    return f"a2a-{session_id}"


class GnmiProvisioner:
    """One provisioner, many devices: `targets` maps ResolvedPath.device names
    (e.g. "srl1") to their gNMI endpoints."""

    def __init__(self, targets: dict[str, GnmiTarget]) -> None:
        self._targets = targets
        # One long-lived connection per device, opened lazily: SR Linux rate-limits
        # gNMI CONNECTIONS (60/min) — a dial-per-operation adapter locks itself out
        # under any real load. Not thread-safe; the controller serializes (v0).
        self._clients: dict[str, object] = {}

    # --- NetworkProvisioner (docs/03 §5) ------------------------------------

    def apply_bandwidth(
        self,
        session_id: str,
        path: ResolvedPath,
        capacity_bps: int,
        qos_class: int,
    ) -> ApplyResult:
        """The M2.2 recipe, one transaction: policer template + ingress attachment.

        `qos_class` is carried in the entitlement but maps to nothing on this
        platform yet (one class in v0); it is recorded in the template's
        statistics-mode-adjacent naming only when classes become real.
        """
        name = _template_name(session_id)
        subif = f"{path.ingress_if}.0"
        rate_kbps = max(capacity_bps // 1000, 1)  # gNMI leaf is kbps
        template = {
            "policer": [
                {
                    "sequence-id": 1,
                    "peak-rate-kbps": rate_kbps,
                    "committed-rate-kbps": rate_kbps,
                    "maximum-burst-size": _BURST_BYTES,
                    "committed-burst-size": _BURST_BYTES,
                    # RFC 7951: a YANG `empty` leaf is encoded as [null], not {}.
                    "violate-action": {"drop": [None]},
                }
            ]
        }
        attachment = {
            "interface-ref": {"interface": path.ingress_if, "subinterface": 0},
            "input": {"policer-templates": {"policer-template": name}},
        }
        try:
            self._client(path.device).set(
                update=[
                    (paths.policer_template(name), template),
                    (paths.qos_interface(subif), attachment),
                ],
                encoding="json_ietf",
            )
        except Exception as err:  # noqa: BLE001 — the port reports, callers decide
            return ApplyResult(ok=False, detail=f"gNMI Set failed: {err}")
        return ApplyResult(ok=True, detail=f"policer {name} @ {path.device}/{subif}")

    def apply_telemetry(
        self,
        session_id: str,
        target: ResolvedNode,
        sensor_paths: list[str],
        collector_endpoint: str,
        sample_interval_s: int,
    ) -> ApplyResult:
        """ADR-007: the telemetry ticket is the RIGHT to configure telemetry export on
        the device. Honor it by writing a real gNMI-dial-out destination to the router
        (SR Linux `grpc-tunnel destination`) pointing at the consumer's collector — the
        router will export toward it. This is symmetric with `apply_bandwidth`: the
        token authorizes a config write, the config lives ON the device (readable back),
        and teardown removes it (stateless, rule 8) — no provider-side forwarder process.
        """
        name = _template_name(session_id)
        host, _, port = collector_endpoint.rpartition(":")
        destination = {
            "address": host or "0.0.0.0",
            "port": int(port) if port.isdigit() else 57400,
            "network-instance": "mgmt",
        }
        try:
            self._client(target.device).set(
                update=[(paths.telemetry_destination(name), destination)], encoding="json_ietf"
            )
        except Exception as err:  # noqa: BLE001 — the port reports, callers decide
            return ApplyResult(ok=False, detail=f"gNMI Set failed: {err}")
        return ApplyResult(
            ok=True,
            detail=f"telemetry export {name} @ {target.device} → {collector_endpoint}",
        )

    def teardown(self, session_id: str) -> ApplyResult:
        """Remove everything named after this session, on every device we know.

        Stateless on purpose: the session's config is FOUND on the router (template
        `a2a-<sid>` + any attachment referencing it), never remembered here — so a
        second call, or a call after a process restart, is the same success (rule 8).
        """
        removed: list[str] = []
        name = _template_name(session_id)
        for device in self._targets:
            try:
                client = self._client(device)
                deletes = self._session_config_on(client, name)
                deletes += self._session_telemetry_on(client, name)
                if deletes:
                    client.set(delete=deletes, encoding="json_ietf")
                    removed.append(device)
            except Exception as err:  # noqa: BLE001
                return ApplyResult(ok=False, detail=f"gNMI teardown failed on {device}: {err}")
        detail = f"removed: {', '.join(removed)}" if removed else "nothing to remove"
        return ApplyResult(ok=True, detail=detail)

    def health(self) -> bool:
        try:
            for device in self._targets:
                self._client(device).capabilities()
        except Exception:  # noqa: BLE001
            return False
        return True

    def close(self) -> None:
        """Drop every cached gNMI connection; idempotent. Reconnects lazily if reused."""
        for client in self._clients.values():
            try:
                client.close()
            except Exception:  # noqa: BLE001 — closing is best-effort by nature
                pass
        self._clients.clear()

    # --- plumbing ------------------------------------------------------------

    def _client(self, device: str):
        try:
            target = self._targets[device]
        except KeyError:
            raise KeyError(
                f"no gNMI target configured for device {device!r} (known: {sorted(self._targets)})"
            ) from None
        if device not in self._clients:
            self._clients[device] = connect(target)
        return self._clients[device]

    def _session_config_on(self, client, template_name: str) -> list[str]:
        """The delete-list for one session on one device, read from the router.

        Ordered attachment-first: the router refuses to delete a template that is
        still referenced, even within one Set transaction.
        """
        deletes: list[str] = []
        config = client.get(path=[paths.QOS_INTERFACES], encoding="json_ietf", datatype="config")
        for update in config["notification"][0].get("update") or []:
            for interface in _denamespace(update["val"] or {}).get("interface", []):
                attached = (
                    interface.get("input", {}).get("policer-templates", {}).get("policer-template")
                )
                if attached == template_name:
                    deletes.append(paths.qos_interface(interface["interface-id"]))
        templates = client.get(
            path=[paths.QOS_POLICER_TEMPLATES], encoding="json_ietf", datatype="config"
        )
        for update in templates["notification"][0].get("update") or []:
            for template in _denamespace(update["val"] or {}).get("policer-template", []):
                if template.get("name") == template_name:
                    deletes.append(paths.policer_template(template_name))
        return deletes

    def _session_telemetry_on(self, client, name: str) -> list[str]:
        """The telemetry-export destinations this session installed (found on the
        router, so teardown is stateless — rule 8)."""
        deletes: list[str] = []
        cfg = client.get(
            path=[paths.TELEMETRY_DESTINATIONS], encoding="json_ietf", datatype="config"
        )
        for update in cfg["notification"][0].get("update") or []:
            for dest in _denamespace(update["val"] or {}).get("destination", []):
                if dest.get("name") == name:
                    deletes.append(paths.telemetry_destination(name))
        return deletes

    def telemetry_config(self, device: str) -> list[dict]:
        """Every a2a telemetry-export destination currently on the router (for the
        inspector) — read live off the device, like the policer readout."""
        client = self._client(device)
        cfg = client.get(
            path=[paths.TELEMETRY_DESTINATIONS], encoding="json_ietf", datatype="config"
        )
        out = []
        for update in cfg["notification"][0].get("update") or []:
            for dest in _denamespace(update["val"] or {}).get("destination", []):
                if dest.get("name", "").startswith("a2a-"):
                    out.append(dest)
        return out


def _denamespace(node):
    """Strip RFC 7951 module prefixes ("srl_nokia-acl-policers:policer-templates" →
    "policer-templates"), recursively. Responses prefix a key wherever the YANG node
    comes from another module (augments!), so plain key lookups silently miss."""
    if isinstance(node, dict):
        return {key.split(":", 1)[-1]: _denamespace(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_denamespace(item) for item in node]
    return node
