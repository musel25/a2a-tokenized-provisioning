"""Tiny shared helpers for the agents tests (importable as a top-level module because
`agents/tests` is on sys.path during the test run)."""

from __future__ import annotations

from a2a_interfaces import BandwidthNeed
from a2a_interfaces.fixtures import WINDOW


def bandwidth_need_for(capacity_bps: int) -> BandwidthNeed:
    """A bandwidth need for a given rate, in the canonical window."""
    return BandwidthNeed(
        src="hostA", dst="hostB", capacity_bps=capacity_bps, qos_class=1, window=WINDOW
    )
