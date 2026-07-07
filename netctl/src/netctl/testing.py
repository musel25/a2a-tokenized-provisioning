"""Lab plumbing for tests and notebooks — how to find the running containerlab nodes.

Mirrors chainmcp.testing's role: one way to locate the lab, everywhere. Not imported
by production code paths.
"""

from __future__ import annotations

import socket
import subprocess
import threading

LAB_NODE = "clab-a2a-srl1"


class DummyCollector:
    """The consumer's endpoint, as 25 lines: a TCP sink that keeps every JSON line.

    This is what the plan's M3.3 calls "a dummy collector" — tests and notebooks
    point `apply_telemetry` at `.endpoint` and read `.lines`."""

    def __init__(self) -> None:
        self._server = socket.create_server(("127.0.0.1", 0))
        self.endpoint = "127.0.0.1:" + str(self._server.getsockname()[1])
        self.lines: list[str] = []
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        try:
            conn, _ = self._server.accept()
            buffer = b""
            while chunk := conn.recv(65536):
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    self.lines.append(line.decode())
        except OSError:
            pass  # closed — normal shutdown

    def stop(self) -> None:
        self._server.close()


def lab_ipv4(node: str = LAB_NODE) -> str | None:
    """The node's IPv4 if the lab is up, else None. Docker is asked directly because
    the lab's /etc/hosts entries are IPv6-only and python-grpc won't dial those
    (docs/07 appendix)."""
    result = subprocess.run(
        ["docker", "inspect", node, "--format", "{{.NetworkSettings.Networks.clab.IPAddress}}"],
        capture_output=True,
        text=True,
    )
    ip = result.stdout.strip()
    return ip if result.returncode == 0 and ip else None
