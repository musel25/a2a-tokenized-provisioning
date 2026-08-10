"""Lab plumbing for tests and notebooks — how to find the running containerlab nodes.

Mirrors chainmcp.testing's role: one way to locate the lab, everywhere. Not imported
by production code paths.
"""

from __future__ import annotations

import subprocess

LAB_NODE = "clab-a2a-srl1"

# The consumer's collector, modelled as its own node on the lab bridge (ADR-008).
# On the bridge and not on the host: bridge→host is dropped on the dev machine,
# bridge→container is not, so a host-side collector looks exactly like a broken
# tunnel. The port is where its gRPC-tunnel server listens.
LAB_COLLECTOR_NODE = "clab-a2a-collector"
COLLECTOR_TUNNEL_PORT = 57401


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


def lab_collector(node: str = LAB_COLLECTOR_NODE) -> str | None:
    """`host:port` for the lab collector's tunnel server, or None if it is not up."""
    ip = lab_ipv4(node)
    return f"{ip}:{COLLECTOR_TUNNEL_PORT}" if ip else None
