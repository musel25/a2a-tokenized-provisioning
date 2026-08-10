"""The shared contract suite (rule 7): every test runs against BOTH provisioners.

A mock with different behavior at the port is a bug — these tests are where that
bug becomes red. The assertions only use the port's own surface (docs/03 §5) plus
`verify_*` helpers that peek behind each implementation appropriately.
"""

from __future__ import annotations

from a2a_interfaces import NetworkProvisioner, ResolvedPath
from a2a_interfaces.fixtures import CAPACITY_50_MBPS, QOS_CLASS, RESOLVED_PATH

from netctl.mock import MockProvisioner
from netctl.testing import lab_collector

SESSION = "contract-test"

# Any address writes the same config, and this suite asserts that the config is
# PRESENT, not that samples arrive — delivery is test_gnmi_lab's job. Pointing at the
# real collector when the lab is up means the tunnel also comes up for free.
LAB_COLLECTOR = lab_collector() or "10.0.0.50:57400"


def _applied_on(provisioner, session_id: str) -> bool:
    """Implementation-appropriate 'is the config there?' — recorded for the mock,
    read back off the router for the real one."""
    if isinstance(provisioner, MockProvisioner):
        return session_id in provisioner.applied
    # No `with`: the provisioner's clients are cached long-lived connections
    # (SR Linux rate-limits dials); context-managing one would close it under
    # the provisioner's feet.
    client = provisioner._client(RESOLVED_PATH.device)
    return bool(provisioner._session_config_on(client, f"a2a-{session_id}"))


def test_satisfies_the_port(provisioner):
    assert isinstance(provisioner, NetworkProvisioner)


def test_health(provisioner):
    assert provisioner.health() is True


def test_apply_bandwidth_then_teardown_roundtrip(provisioner):
    result = provisioner.apply_bandwidth(SESSION, RESOLVED_PATH, CAPACITY_50_MBPS, QOS_CLASS)
    assert result.ok, result.detail
    assert _applied_on(provisioner, SESSION)

    down = provisioner.teardown(SESSION)
    assert down.ok, down.detail
    assert not _applied_on(provisioner, SESSION)


def test_teardown_is_idempotent(provisioner):
    provisioner.apply_bandwidth(SESSION, RESOLVED_PATH, CAPACITY_50_MBPS, QOS_CLASS)
    assert provisioner.teardown(SESSION).ok
    assert provisioner.teardown(SESSION).ok  # second call: success, not error (rule 8)


def test_teardown_of_unknown_session_succeeds(provisioner):
    assert provisioner.teardown("never-existed").ok


def _telemetry_on(provisioner, session_id: str) -> bool:
    """'Is the telemetry export there?' — and there means BOTH nodes (ADR-008).

    The destination alone reads back perfectly and exports nothing, so a helper that
    looked only for it would call a dead session live.
    """
    if isinstance(provisioner, MockProvisioner):
        applied = provisioner.applied.get(session_id)
        return bool(applied) and set(applied["nodes"]) == {"destination", "tunnel"}
    client = provisioner._client("srl1")  # see _applied_on on why not `with`
    found = provisioner._session_telemetry_on(client, f"a2a-{session_id}")
    return len(found) == 2


def test_apply_telemetry_then_teardown_roundtrip(provisioner):
    """The telemetry ticket is the right to configure telemetry export on the device
    (ADR-007): apply writes a real export, teardown removes it. Export means the
    destination and the tunnel that dials it (ADR-008)."""
    from a2a_interfaces.fixtures import TELEMETRY_NEED
    from a2a_interfaces.models import ResolvedNode

    result = provisioner.apply_telemetry(
        SESSION,
        ResolvedNode(device="srl1"),
        TELEMETRY_NEED.sensor_paths,
        LAB_COLLECTOR,
        TELEMETRY_NEED.sample_interval_s,
    )
    assert result.ok, result.detail
    assert _telemetry_on(provisioner, SESSION)

    assert provisioner.teardown(SESSION).ok
    assert not _telemetry_on(provisioner, SESSION)
    assert provisioner.teardown(SESSION).ok  # telemetry teardown idempotent too (rule 8)


def test_telemetry_teardown_deletes_the_tunnel_before_the_destination():
    """gNMI-only: the tunnel holds a leafref to the destination, so the router refuses
    to delete the destination while the tunnel still names it — even inside one Set.

    Ordering is invisible at the port (the mock has no delete list), so it is asserted
    here against a stubbed client rather than pretended into the shared suite.
    """
    from netctl.connect import GnmiTarget
    from netctl.provisioner import GnmiProvisioner

    name = f"a2a-{SESSION}"

    class _Client:
        """Returns both nodes, destination-first — the order the router reports them,
        which is the order teardown must NOT use."""

        def get(self, **_kwargs):
            return {
                "notification": [
                    {
                        "update": [
                            {
                                "val": {
                                    "destination": [{"name": name}],
                                    "tunnel": [{"name": name}],
                                }
                            }
                        ]
                    }
                ]
            }

    deletes = GnmiProvisioner({"srl1": GnmiTarget(host="127.0.0.1")})._session_telemetry_on(
        _Client(), name
    )
    assert deletes == [
        f"/system/grpc-tunnel/tunnel[name={name}]",
        f"/system/grpc-tunnel/destination[name={name}]",
    ]


def test_unknown_device_is_a_loud_error():
    """gNMI-only check: a device with no configured target must raise, not guess.
    (The mock has no device map — nothing to test on that side.)"""
    from netctl.connect import GnmiTarget
    from netctl.provisioner import GnmiProvisioner

    lonely = GnmiProvisioner({"srl1": GnmiTarget(host="127.0.0.1")})
    result = lonely.apply_bandwidth(
        SESSION, ResolvedPath(device="unknown-router", ingress_if="e1", egress_if="e2"), 1000, 1
    )
    assert not result.ok
    assert "unknown-router" in result.detail
