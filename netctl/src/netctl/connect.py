"""gNMI connection plumbing — the M3.1 TLS recipe, encapsulated once.

The containerized router presents a self-signed leaf cert, python-grpc refuses to
skip verification, and the lab's /etc/hosts entries are IPv6-only (docs/07 appendix).
Nothing above this module should ever know any of that: give `GnmiTarget` a host and
credentials, get a connected client.
"""

from __future__ import annotations

import ssl
import tempfile
from dataclasses import dataclass, field

from pygnmi.client import gNMIclient


@dataclass(frozen=True)
class GnmiTarget:
    """How to reach one device's gNMI server. `tls_name` must match the SAN inside
    the device's certificate (for the lab's self-generated leaf: the node's short
    name, e.g. "srl1" — NOT the container hostname)."""

    host: str
    port: int = 57400
    username: str = "admin"
    password: str = "NokiaSrl1!"  # SR Linux default; lab only
    tls_name: str = field(default="")


def connect(target: GnmiTarget) -> gNMIclient:
    """Trust-on-first-use: fetch the device's leaf cert and hand it to grpc as the
    root (a self-signed cert is its own CA). Caller owns the client (context-manage
    or .close())."""
    pem = ssl.get_server_certificate((target.host, target.port))
    cert_file = tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False)
    cert_file.write(pem)
    cert_file.close()
    client = gNMIclient(
        target=(target.host, target.port),
        username=target.username,
        password=target.password,
        path_root=cert_file.name,
        override=target.tls_name or None,
    )
    client.connect()
    return client
