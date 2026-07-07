"""The M3.2 acceptance test: M2.2's iperf evidence, reproduced by ONE function call.

Needs the live lab + docker; skips otherwise (CI runs the mock leg of the contract
suite instead). The shim tick between apply and measure is ADR-006's missing ASIC —
the lab fixture's job, never netctl's.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from a2a_interfaces.fixtures import CAPACITY_50_MBPS, QOS_CLASS, RESOLVED_PATH
from netctl.connect import GnmiTarget
from netctl.provisioner import GnmiProvisioner
from netctl.testing import lab_ipv4

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


def test_one_call_configures_telemetry_export_on_the_device():
    """The M3.3 acceptance test (ADR-007, revised): the telemetry ticket is the RIGHT to
    configure telemetry export on the device. apply_telemetry writes a real export
    destination onto srl1 (readable back off the router); teardown removes it."""
    from a2a_interfaces.models import ResolvedNode

    provisioner = GnmiProvisioner({"srl1": GnmiTarget(host=lab_ipv4(), tls_name="srl1")})
    session = "lab-telemetry"
    try:
        result = provisioner.apply_telemetry(
            session,
            ResolvedNode(device="srl1"),
            ["/interface[name=ethernet-1/1]/statistics"],
            "10.0.0.50:57400",
            sample_interval_s=10,
        )
        assert result.ok, result.detail

        # the config really landed — read OUR destination back off the router (other a2a
        # sessions may coexist on the shared lab; assert only on this test's name)
        mine = [d for d in provisioner.telemetry_config("srl1") if d["name"] == f"a2a-{session}"]
        assert mine, provisioner.telemetry_config("srl1")
        assert mine[0]["address"] == "10.0.0.50" and mine[0]["port"] == 57400

        assert provisioner.teardown(session).ok
        left = [d for d in provisioner.telemetry_config("srl1") if d["name"] == f"a2a-{session}"]
        assert left == []  # OUR config removed from the device
        assert provisioner.teardown(session).ok  # idempotent (rule 8)
    finally:
        provisioner.close()
