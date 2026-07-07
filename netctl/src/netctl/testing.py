"""Lab plumbing for tests and notebooks — how to find the running containerlab nodes.

Mirrors chainmcp.testing's role: one way to locate the lab, everywhere. Not imported
by production code paths.
"""

from __future__ import annotations

import subprocess

LAB_NODE = "clab-a2a-srl1"


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
