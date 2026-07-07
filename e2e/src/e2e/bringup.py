"""One-command bring-up (M6.1): Anvil → deploy → controller, with healthchecks.

`just up` starts the chain layer and the controller as plain background processes and
waits until each answers a healthcheck; `just down` stops them. The SR Linux lab is
brought up separately (`containerlab deploy`, ~1 min, ~2 GB) and wired in via
`SKELETON_PROFILE=chain+net` — it is deliberately NOT part of the default `up` so the
chain-only stack (which every e2e chain test needs) comes up in seconds.

Plain processes, no containers of our own (docs/01 M6.1) — the only container is the lab
that already is one. A PID/URL manifest in `e2e/runs/current.json` lets `down` find what
`up` started, even across shells.
"""

from __future__ import annotations

import json
import signal
import socket
import subprocess
import time
from dataclasses import dataclass

from chainmcp.artifacts import find_contracts_dir, load_deployment

REPO = find_contracts_dir().parent
RUN_DIR = REPO / "e2e" / "runs"
MANIFEST = RUN_DIR / "current.json"

ANVIL_PORT = 8545
CONTROLLER_PORT = 8000
STORY_TIME = 1757944800 - 1680  # 13:32, before Ada's window
ANVIL_KEY0 = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"


@dataclass
class Manifest:
    anvil_pid: int
    controller_pid: int
    rpc_url: str
    controller_url: str

    def save(self) -> None:
        RUN_DIR.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(json.dumps(self.__dict__, indent=2))


def _wait(check, what: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if check():
                return
        except Exception:
            pass
        time.sleep(0.3)
    raise RuntimeError(f"{what} did not come up within {timeout}s")


def _port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def up() -> Manifest:
    """Start Anvil + deploy + controller; block until all healthy; write the manifest."""
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    # start_new_session so each process leads its own group — `down` kills the whole
    # group, catching grandchildren (uvicorn is a child of `uv run`, not `up` directly).
    anvil = subprocess.Popen(
        ["anvil", "--port", str(ANVIL_PORT), "--timestamp", str(STORY_TIME), "--silent"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    _wait(lambda: _port_open(ANVIL_PORT), "anvil")

    subprocess.run(
        [
            "forge",
            "script",
            "script/Deploy.s.sol",
            "--rpc-url",
            f"http://127.0.0.1:{ANVIL_PORT}",
            "--broadcast",
            "--private-key",
            ANVIL_KEY0,
        ],
        cwd=REPO / "contracts",
        check=True,
        capture_output=True,
    )
    deployment = load_deployment()

    controller = subprocess.Popen(
        [
            "uv",
            "run",
            "python",
            "-m",
            "e2e.controller_server",
            "--rpc-url",
            f"http://127.0.0.1:{ANVIL_PORT}",
            "--port",
            str(CONTROLLER_PORT),
        ],
        cwd=REPO,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    _wait(lambda: _controller_healthy(CONTROLLER_PORT), "controller")

    manifest = Manifest(
        anvil_pid=anvil.pid,
        controller_pid=controller.pid,
        rpc_url=f"http://127.0.0.1:{ANVIL_PORT}",
        controller_url=f"http://127.0.0.1:{CONTROLLER_PORT}",
    )
    manifest.save()
    _ = deployment  # deployed; addresses live in contracts/deployments/anvil.json
    return manifest


def _controller_healthy(port: int) -> bool:
    import httpx

    # any answer (even a 404 on an unknown session) means the ASGI app is serving
    return httpx.get(
        f"http://127.0.0.1:{port}/v0/sessions/health-probe", timeout=1
    ).status_code in (
        200,
        404,
    )


def down() -> None:
    """Stop whatever `up` started (from the manifest); idempotent. Kills each PROCESS
    GROUP so uvicorn (grandchild of `uv run`) dies with its parent."""
    import os

    if not MANIFEST.exists():
        return
    data = json.loads(MANIFEST.read_text())
    for pid in (data.get("controller_pid"), data.get("anvil_pid")):
        if not pid:
            continue
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
    # wait for the sockets to actually release (SIGTERM is async); escalate if needed
    for port in (CONTROLLER_PORT, ANVIL_PORT):
        deadline = time.monotonic() + 5
        while _port_open(port) and time.monotonic() < deadline:
            time.sleep(0.1)
    MANIFEST.unlink(missing_ok=True)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "down":
        down()
        print("down: stack stopped")
    else:
        m = up()
        print(f"up: anvil {m.rpc_url}  controller {m.controller_url}")


def _sigterm(*_):
    down()


signal.signal(signal.SIGTERM, _sigterm)
