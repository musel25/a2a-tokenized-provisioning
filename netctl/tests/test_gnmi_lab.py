"""The M3.2 acceptance test: M2.2's iperf evidence, reproduced by ONE function call.

Needs the live lab + docker; skips otherwise (CI runs the mock leg of the contract
suite instead). The shim tick between apply and measure is ADR-006's missing ASIC —
the lab fixture's job, never netctl's.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest

from a2a_interfaces.fixtures import CAPACITY_50_MBPS, QOS_CLASS, RESOLVED_PATH
from netctl.connect import GnmiTarget
from netctl.provisioner import GnmiProvisioner
from netctl.testing import LAB_COLLECTOR_NODE, lab_collector, lab_ipv4

SHIM = Path(__file__).parents[2] / "netlab" / "mirror-policer-to-tc.sh"

pytestmark = pytest.mark.skipif(
    lab_ipv4() is None, reason="needs the live lab (containerlab deploy)"
)


def _iperf_mbps(seconds: int = 6) -> float:
    """Received rate of a 100 Mbit/s UDP offer — deterministic on both sides of the
    policer, unlike single-stream TCP whose CPU-bound ceiling wobbles (55–75)."""
    subprocess.run(
        ["docker", "exec", "-d", "clab-a2a-hostB", "iperf3", "-s", "-p", "5210", "-1"],
        check=False,
    )
    out = subprocess.run(
        [
            "docker",
            "exec",
            "clab-a2a-hostA",
            "iperf3",
            "-c",
            "10.10.2.10",
            "-p",
            "5210",
            "-t",
            str(seconds),
            "-u",
            "-b",
            "100M",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    summary = json.loads(out)["end"]["sum"]
    # iperf3's UDP client JSON reports the SENDER rate; the received rate is what
    # survived the policer: sent × (1 − loss).
    return summary["bits_per_second"] * (1 - summary["lost_percent"] / 100) / 1e6


def _shim_tick() -> None:
    subprocess.run([str(SHIM)], check=True, capture_output=True)


def test_one_call_reproduces_the_m22_plateau():
    provisioner = GnmiProvisioner({"srl1": GnmiTarget(host=lab_ipv4(), tls_name="srl1")})
    session = "lab-accept"
    try:
        result = provisioner.apply_bandwidth(session, RESOLVED_PATH, CAPACITY_50_MBPS, QOS_CLASS)
        assert result.ok, result.detail
        _shim_tick()
        shaped = _iperf_mbps()
        # 100M offered through a 50M policer: the received rate IS the plateau
        assert 40.0 < shaped < 55.0, f"expected ~50 Mbps plateau, measured {shaped:.1f}"
    finally:
        assert provisioner.teardown(session).ok  # cleanup even on failure (rule 8)
        _shim_tick()

    unshaped = _iperf_mbps()
    assert unshaped > 85.0, (
        f"teardown should let the full 100M offer through again (shaped {shaped:.1f}, "
        f"after {unshaped:.1f})"
    )


def _collector_samples() -> int:
    """Samples the consumer's collector has received, counted in its own output.

    Read from the collector's log rather than from the router: the question is what
    ARRIVED at the buyer, and the router's view cannot answer that.
    """
    out = subprocess.run(
        ["docker", "logs", LAB_COLLECTOR_NODE], capture_output=True, text=True, check=False
    )
    return (out.stdout + out.stderr).count('"interface/statistics/in-octets"')


def _await_tunnel(provisioner, session: str, want: str, timeout_s: float = 45.0) -> str | None:
    """Poll this session's tunnel oper-state until it reads `want`, else return the last
    value seen. Dial-out is a retry loop on the router's side, so `up` takes seconds."""
    deadline = time.monotonic() + timeout_s
    state = None
    while time.monotonic() < deadline:
        mine = [d for d in provisioner.telemetry_config("srl1") if d["name"] == f"a2a-{session}"]
        state = mine[0]["oper_state"] if mine else None
        if state == want:
            return state
        time.sleep(2.0)
    return state


def test_one_call_configures_telemetry_export_on_the_device():
    """The M3.3 acceptance test (ADR-007/008): the telemetry ticket is the RIGHT to
    configure telemetry export on the device. apply_telemetry writes BOTH grpc-tunnel
    nodes onto srl1 (readable back off the router); teardown removes them.

    The two-node assertion is the point. An earlier version wrote the destination
    alone, and this test passed against config that could never export.
    """
    from a2a_interfaces.models import ResolvedNode

    provisioner = GnmiProvisioner({"srl1": GnmiTarget(host=lab_ipv4(), tls_name="srl1")})
    session = "lab-telemetry"
    collector = lab_collector() or "10.0.0.50:57400"
    host, _, port = collector.rpartition(":")
    try:
        result = provisioner.apply_telemetry(
            session,
            ResolvedNode(device="srl1"),
            ["/interface[name=ethernet-1/1]/statistics"],
            collector,
            sample_interval_s=10,
        )
        assert result.ok, result.detail

        # the config really landed — read OUR export back off the router (other a2a
        # sessions may coexist on the shared lab; assert only on this test's name)
        mine = [d for d in provisioner.telemetry_config("srl1") if d["name"] == f"a2a-{session}"]
        assert mine, provisioner.telemetry_config("srl1")
        assert mine[0]["address"] == host and mine[0]["port"] == int(port)
        assert mine[0]["tunnel"] is True, "destination without a tunnel exports nothing"

        assert provisioner.teardown(session).ok
        left = [d for d in provisioner.telemetry_config("srl1") if d["name"] == f"a2a-{session}"]
        assert left == []  # OUR config removed from the device
        assert provisioner.teardown(session).ok  # idempotent (rule 8)
    finally:
        provisioner.close()


@pytest.mark.skipif(lab_collector() is None, reason="needs the lab collector node")
def test_the_entitlements_config_is_what_makes_samples_flow():
    """ADR-008's causal claim, end to end: the buyer receives telemetry BECAUSE the
    entitlement's config is on the router, and stops when teardown removes it.

    This is the telemetry twin of the policer's iperf plateau — once-established
    evidence that a committed config means what it says, not a per-run assertion.
    """
    from a2a_interfaces.models import ResolvedNode

    provisioner = GnmiProvisioner({"srl1": GnmiTarget(host=lab_ipv4(), tls_name="srl1")})
    session = "lab-delivery"
    try:
        assert provisioner.apply_telemetry(
            session,
            ResolvedNode(device="srl1"),
            ["/interface[name=ethernet-1/1]/statistics"],
            lab_collector(),
            sample_interval_s=5,
        ).ok
        assert _await_tunnel(provisioner, session, "up") == "up", "tunnel never dialled out"

        before = _collector_samples()
        time.sleep(15.0)
        during = _collector_samples()
        assert during > before, "tunnel up but nothing arrived at the collector"

        assert provisioner.teardown(session).ok
        # The router stops mid-stream, so allow the in-flight sample to land, then
        # require silence across several sample intervals.
        time.sleep(3.0)
        settled = _collector_samples()
        time.sleep(20.0)
        assert _collector_samples() == settled, "samples still arriving after teardown"
    finally:
        provisioner.teardown(session)
        provisioner.close()
