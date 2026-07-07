"""Provisioner fixtures: the mock always; the real one when the lab is running.

`provisioner` is parametrized over both implementations — THE mechanism of rule 7:
one contract suite, two adapters, any behavioral divergence at the port is a red test.
The gnmi variant skips (never fails) without a live lab; CI runs the mock leg.
"""

from __future__ import annotations

import pytest

from netctl.connect import GnmiTarget
from netctl.mock import MockProvisioner
from netctl.provisioner import GnmiProvisioner
from netctl.testing import lab_ipv4


@pytest.fixture(scope="session")
def _gnmi_provisioner():
    """ONE provisioner (= one cached gNMI connection) for the whole session: SR Linux
    rate-limits connections per minute, so per-test dialing can lock the suite out of
    its own router. (The lab also raises the limit in srl1-init.cli — belt and braces.)"""
    ip = lab_ipv4()
    if ip is None:
        pytest.skip("gnmi leg needs the live lab (containerlab deploy -t netlab/topology.clab.yml)")
    prov = GnmiProvisioner({"srl1": GnmiTarget(host=ip, tls_name="srl1")})
    yield prov
    prov.close()


@pytest.fixture(params=["mock", "gnmi"])
def provisioner(request):
    if request.param == "mock":
        yield MockProvisioner()
        return
    prov = request.getfixturevalue("_gnmi_provisioner")
    yield prov
    prov.teardown("contract-test")  # idempotent per-test cleanup even after failures (rule 8)
