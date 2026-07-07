"""The demo (M6.2/M6.3/M6.5): both service types, one narrated, dashboard-emitting run.

Runs the real lifecycle end to end — Anvil + the controller + the SR Linux lab — for
BANDWIDTH (M6.2: iperf plateau, auto-teardown at chain-time t1) and then TELEMETRY
(M6.3: the telemetry ticket configures export on the device). Every step emits a DashboardEvent, so the whole
thing is watchable in the Streamlit view (M6.4). This is the demo script (M6.5) as code:
`uv run python -m e2e.demo` prints the narration and writes e2e/runs/demo/events.jsonl.

M6.3's thesis result — *how little changes between the two service types* — is measured
here: the SAME controller, SAME auth, SAME session machine; only the translator + the
provisioner call differ. The demo asserts that by driving both through one code path.

Needs Anvil + forge artifacts + the live lab.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from a2a_interfaces.fixtures import (
    CANONICAL_OFFER,
    RESOLVED_NODE,
    TELEMETRY_NEED,
)
from chainmcp import ChainClient
from chainmcp.testing import ANVIL_KEYS, launch_anvil
from netctl.connect import GnmiTarget
from netctl.provisioner import GnmiProvisioner
from netctl.testing import lab_ipv4

from e2e.dashboard.emitter import RunLog

STORY_TIME = 1757944800 - 1680
SHIM = Path(__file__).resolve().parents[3] / "netlab" / "mirror-policer-to-tc.sh"


def _iperf_udp_received_mbps() -> float:
    subprocess.run(
        ["docker", "exec", "-d", "clab-a2a-hostB", "iperf3", "-s", "-p", "5301", "-1"], check=False
    )
    import json

    out = subprocess.run(
        [
            "docker",
            "exec",
            "clab-a2a-hostA",
            "iperf3",
            "-c",
            "10.10.2.10",
            "-p",
            "5301",
            "-t",
            "4",
            "-u",
            "-b",
            "100M",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    s = json.loads(out)["end"]["sum"]
    return s["bits_per_second"] * (1 - s["lost_percent"] / 100) / 1e6


def run() -> dict:
    # Refuse to run (and to clobber any existing demo events) unless the lab is up —
    # this demo drives a real router. For a stack-free dashboard, use
    # `python -m e2e.dashboard.demo_run` instead.
    lab = lab_ipv4()
    if lab is None:
        raise SystemExit(
            "e2e.demo needs the SR Linux lab up:\n"
            "  containerlab deploy -t netlab/topology.clab.yml\n"
            "(for a stack-free dashboard, run: uv run python -m e2e.dashboard.demo_run)"
        )

    log = RunLog(Path(__file__).resolve().parents[3] / "e2e" / "runs" / "demo" / "events.jsonl")
    log.path.unlink(missing_ok=True)
    log = RunLog(log.path)
    anvil = launch_anvil(timestamp=STORY_TIME)
    provisioner = GnmiProvisioner({"srl1": GnmiTarget(host=lab, tls_name="srl1")})
    bell = ChainClient(anvil.rpc_url, ANVIL_KEYS["bell"], deployment=anvil.deployment)
    ada = ChainClient(anvil.rpc_url, ANVIL_KEYS["ada"], deployment=anvil.deployment)
    measured = {}
    try:
        ada.faucet(100 * 10**18)

        # --- BANDWIDTH (M6.2) ------------------------------------------------
        now = ada.chain_time()
        log.emit(now, "fulfill", "chain", "Ada buys a 50 Mbps ticket from Bell")
        _, bw_id = ada.approve_and_fulfill(bell.sign_offer(CANONICAL_OFFER))
        anvil.increase_time(ada._w3, 1800)  # into the window

        session = f"demo-bw-{bw_id}"
        log.emit(
            ada.chain_time(), "apply_bandwidth", "network", "gNMI Set: policer 50 Mbps on srl1"
        )
        assert provisioner.apply_bandwidth(session, _resolved_path(), 50_000_000, 1).ok
        subprocess.run([str(SHIM)], capture_output=True)  # ADR-006 shim tick
        measured["bandwidth_shaped_mbps"] = _iperf_udp_received_mbps()
        print(f"  bandwidth: 100M offered → {measured['bandwidth_shaped_mbps']:.1f} Mbps (policed)")

        log.emit(ada.chain_time(), "teardown", "network", "window ends → policer removed")
        provisioner.teardown(session)
        subprocess.run([str(SHIM)], capture_output=True)
        measured["bandwidth_after_mbps"] = _iperf_udp_received_mbps()
        print(f"  bandwidth: after teardown → {measured['bandwidth_after_mbps']:.1f} Mbps (full)")

        # --- TELEMETRY (M6.3) — the SAME provisioner, one different call -------
        # The telemetry ticket is the right to configure telemetry export on the device
        # (ADR-007): apply writes a real dial-out destination to srl1, teardown removes it.
        log.emit(
            ada.chain_time(),
            "apply_telemetry",
            "network",
            "gNMI Set: telemetry export destination on srl1 → Ada's collector",
        )
        assert provisioner.apply_telemetry(
            "demo-tel", RESOLVED_NODE, TELEMETRY_NEED.sensor_paths, "10.0.0.50:57400", 10
        ).ok
        dests = provisioner.telemetry_config("srl1")  # read the config back off the router
        measured["telemetry_export"] = dests[0]["name"] if dests else None
        print(f"  telemetry: export {measured['telemetry_export']} configured on srl1")
        provisioner.teardown("demo-tel")

        log.emit(ada.chain_time(), "report", "agent", "both services delivered, then withdrawn")
        return measured
    finally:
        for c in (bell, ada):
            c.close()
        provisioner.teardown("demo-bw-7")
        provisioner.close()
        anvil.stop()


def _resolved_path():
    from a2a_interfaces.fixtures import RESOLVED_PATH

    return RESOLVED_PATH


if __name__ == "__main__":
    print("a2a demo — bandwidth then telemetry, one code path:")
    result = run()
    print("\nmeasured:", result)
    print("watch it:  uv run --group demo streamlit run e2e/src/e2e/dashboard/app.py")
