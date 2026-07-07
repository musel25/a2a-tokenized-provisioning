"""M3.1 — the pygnmi smoke test: prove Python can drive the router's three exchanges.

Get an interface's oper-state (read state), Set a description (write config), Get the
description back (the write survived). Uses the same json_ietf encoding the M2.3 gnmic
recipe pinned (docs/07 §7.2).

TLS, the hard-won part (docs/07 appendix): the containerized router presents a SELF-SIGNED
leaf cert (CN=srl1, SAN DNS:srl1 — the lab CA never reaches the node under sudoless
containerlab), and pygnmi's `skipverify` cannot cope with it (grpc still verifies →
CERTIFICATE_VERIFY_FAILED under the hood, surfacing as a timeout). The reliable recipe
is trust-on-first-use: fetch the leaf over plain TLS, hand it to grpc as the root (a
self-signed cert is its own CA), and override SNI to the cert's OWN name, not the
container's hostname.

Run against a live lab:  uv run python -m netctl.gnmi_smoke [host [port]]
(default host: clab-a2a-srl1's IPv4, resolved the way docs/07 §3 shows)
"""

from __future__ import annotations

import ssl
import subprocess
import sys
import tempfile

from pygnmi.client import gNMIclient

CREDS = {"username": "admin", "password": "NokiaSrl1!"}  # SR Linux defaults; lab only
CERT_NAME = "srl1"  # the SAN inside the router's self-generated cert
IF_PATH = "/interface[name=ethernet-1/1]"


def container_ipv4(name: str = "clab-a2a-srl1") -> str:
    """The lab's /etc/hosts entry is IPv6-only, which python-grpc won't dial; ask
    docker for the IPv4 instead."""
    return subprocess.run(
        ["docker", "inspect", name, "--format", "{{.NetworkSettings.Networks.clab.IPAddress}}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def fetch_leaf_cert(host: str, port: int) -> str:
    """Trust-on-first-use: the router's self-signed leaf, written to a temp file."""
    pem = ssl.get_server_certificate((host, port))
    handle = tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False)
    handle.write(pem)
    handle.close()
    return handle.name


def main() -> None:
    host = sys.argv[1] if len(sys.argv) > 1 else container_ipv4()
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 57400

    with gNMIclient(
        target=(host, port),
        path_root=fetch_leaf_cert(host, port),
        override=CERT_NAME,
        **CREDS,
    ) as gc:
        print(f"connected: gNMI {gc.capabilities()['gnmi_version']} at {host}:{port}")

        state = gc.get(path=[IF_PATH + "/oper-state"], encoding="json_ietf")
        oper = state["notification"][0]["update"][0]["val"]
        print(f"Get   oper-state e1-1  -> {oper}")

        gc.set(
            update=[(IF_PATH, {"description": "smoke-test was here (M3.1)"})], encoding="json_ietf"
        )
        print("Set   description e1-1 -> committed")

        back = gc.get(path=[IF_PATH + "/description"], encoding="json_ietf")
        desc = back["notification"][0]["update"][0]["val"]
        print(f"Get   description e1-1 -> {desc!r}")
        assert desc == "smoke-test was here (M3.1)", "the Set did not survive!"
        print("smoke: all three exchanges green")


if __name__ == "__main__":
    main()
