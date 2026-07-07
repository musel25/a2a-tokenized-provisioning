"""M6.2/M6.3 — the two e2e runs, as one test: bandwidth plateau + telemetry samples,
both through one code path. Needs Anvil + forge + the live lab; skips otherwise."""

from __future__ import annotations

import pytest

from chainmcp.testing import anvil_available, artifacts_available
from netctl.testing import lab_ipv4

pytestmark = pytest.mark.skipif(
    not (anvil_available() and artifacts_available() and lab_ipv4()),
    reason="the e2e demo needs Anvil + forge artifacts + the live lab",
)


def test_bandwidth_and_telemetry_e2e():
    from e2e.demo import run

    measured = run()
    # M6.2: iperf shows the policer, then its removal
    assert 40 < measured["bandwidth_shaped_mbps"] < 55, measured
    assert measured["bandwidth_after_mbps"] > 85, measured
    # M6.3: telemetry samples reached the consumer's collector
    assert measured["telemetry_samples"] >= 2, measured
