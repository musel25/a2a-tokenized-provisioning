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

# Which gRPC server instance a tunneled collector lands on (ADR-008). NOT `mgmt`:
# mgmt serves [gnmi, gnsi], so a tunnel target bound there would hand the buyer of
# *monitoring* a session carrying gNOI too — reboot, file, os. This instance is
# provisioned with gnmi alone (netlab/srl1-init.cli). A provisioning convention like
# _BURST_BYTES, not topology: it is the same name on every device netctl drives.
_TUNNEL_GRPC_SERVER = "telemetry"


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
        the device. Honor it by writing a real gNMI dial-out to the router pointing at
        the consumer's collector — the router then exports toward it. This is symmetric
        with `apply_bandwidth`: the token authorizes a config write, the config lives ON
        the device (readable back), and teardown removes it (stateless, rule 8) — no
        provider-side forwarder process.

        ADR-008: that takes BOTH grpc-tunnel nodes, written in one Set. The destination
        is only an address book; the tunnel is what dials it and registers the target a
        collector subscribes through. An earlier version wrote the destination alone —
        config that read back perfectly and exported nothing, even to a live collector.

        `sensor_paths` and `sample_interval_s` are terms of the entitlement but are NOT
        written here, and that is a real gap rather than an oversight: the tunnel hands
        the collector a gNMI session, and which paths it may then read is authorization
        that lives in gNSI pathz, not in this config tree (ADR-008 measured the cheaper
        role-based route and found it denies every read on this image). A collector can
        subscribe outside the paths it bought.
        """
        name = _template_name(session_id)
        host, _, port = collector_endpoint.rpartition(":")
        destination = {
            "address": host or "0.0.0.0",
            "port": int(port) if port.isdigit() else 57400,
            "network-instance": "mgmt",
        }
        tunnel = {
            "admin-state": "enable",
            # References the destination above by name — the leafref that forces
            # teardown to delete this node FIRST (see _session_telemetry_on).
            "destination": [{"name": name, "admin-state": "enable"}],
            "target": [
                {
                    "name": target.device,
                    "id": {"node-name": [None]},  # empty-type leaf: the router's own name
                    "type": {"gnmi-gnoi-server": _TUNNEL_GRPC_SERVER},
                }
            ],
        }
        try:
            self._client(target.device).set(
                update=[
                    (paths.telemetry_destination(name), destination),
                    (paths.telemetry_tunnel(name), tunnel),
                ],
                encoding="json_ietf",
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
        """The telemetry-export config this session installed (found on the router, so
        teardown is stateless — rule 8).

        Ordered tunnel-first: the tunnel holds a leafref to the destination, and the
        router refuses to delete a destination still referenced — the same ordering
        lesson as the policer attachment in `_session_config_on`. Deleting the tunnel
        is also what actually stops delivery; the destination outlives it silently.
        """
        tunnels: list[str] = []
        destinations: list[str] = []
        cfg = client.get(
            path=[paths.TELEMETRY_DESTINATIONS], encoding="json_ietf", datatype="config"
        )
        for update in cfg["notification"][0].get("update") or []:
            node = _denamespace(update["val"] or {})
            for tunnel in node.get("tunnel", []):
                if tunnel.get("name") == name:
                    tunnels.append(paths.telemetry_tunnel(name))
            for dest in node.get("destination", []):
                if dest.get("name") == name:
                    destinations.append(paths.telemetry_destination(name))
        return tunnels + destinations

    def telemetry_config(self, device: str, with_state: bool = False) -> list[dict]:
        """Every a2a telemetry export currently on the router (for the inspector) —
        read live off the device, like the policer readout.

        Each entry carries the destination's fields plus `tunnel`: whether the active
        half exists. Reading the destination alone would report a session as present
        that cannot export anything (ADR-008), which is the readout that hid the gap
        in the first place.

        `with_state=True` adds the router's own `oper_state` for the tunnel, at the
        cost of a SECOND gNMI request. Off by default because this function is called
        from teardown-polling loops, and SR Linux budgets gNMI at 600/min — doubling
        the reads there exhausts the budget mid-campaign. Callers that poll ask for
        config only; the dashboard and the lab tests, which read occasionally, ask for
        state. `oper_state` is None when it was not read.
        """
        client = self._client(device)
        cfg = client.get(
            path=[paths.TELEMETRY_DESTINATIONS], encoding="json_ietf", datatype="config"
        )
        destinations, tunnels = [], set()
        for update in cfg["notification"][0].get("update") or []:
            node = _denamespace(update["val"] or {})
            destinations += [
                d for d in node.get("destination", []) if d.get("name", "").startswith("a2a-")
            ]
            tunnels |= {t.get("name") for t in node.get("tunnel", [])}
        oper = self._tunnel_oper_states(client) if with_state else {}
        return [
            {**dest, "tunnel": dest["name"] in tunnels, "oper_state": oper.get(dest["name"])}
            for dest in destinations
        ]

    @staticmethod
    def _tunnel_oper_states(client) -> dict[str, str]:
        """name → oper-state for every grpc tunnel, or {} if state is unreadable.

        Best-effort: an inspector readout must not fail because the state branch
        moved. The config half above is the load-bearing part.
        """
        try:
            state = client.get(
                path=[paths.TELEMETRY_DESTINATIONS], encoding="json_ietf", datatype="state"
            )
        except Exception:  # noqa: BLE001 — see docstring
            return {}
        out: dict[str, str] = {}
        for update in state["notification"][0].get("update") or []:
            for tunnel in _denamespace(update["val"] or {}).get("tunnel", []):
                out[tunnel.get("name")] = tunnel.get("oper-state")
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
