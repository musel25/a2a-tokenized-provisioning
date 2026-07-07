"""The shared contract suite (rule 7): every test runs against BOTH provisioners.

A mock with different behavior at the port is a bug — these tests are where that
bug becomes red. The assertions only use the port's own surface (docs/03 §5) plus
`verify_*` helpers that peek behind each implementation appropriately.
"""

from __future__ import annotations

from a2a_interfaces import NetworkProvisioner, ResolvedPath
from a2a_interfaces.fixtures import CAPACITY_50_MBPS, QOS_CLASS, RESOLVED_PATH

from netctl.mock import MockProvisioner

SESSION = "contract-test"


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


def test_apply_telemetry_then_teardown_roundtrip(provisioner):
    """The telemetry ticket is the right to configure telemetry export on the device
    (ADR-007): apply writes a real export destination, teardown removes it."""
    from a2a_interfaces.fixtures import TELEMETRY_NEED
    from a2a_interfaces.models import ResolvedNode

    result = provisioner.apply_telemetry(
        SESSION,
        ResolvedNode(device="srl1"),
        TELEMETRY_NEED.sensor_paths,
        "10.0.0.50:57400",
        TELEMETRY_NEED.sample_interval_s,
    )
    assert result.ok, result.detail
    assert provisioner.teardown(SESSION).ok
    assert provisioner.teardown(SESSION).ok  # telemetry teardown idempotent too (rule 8)


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
