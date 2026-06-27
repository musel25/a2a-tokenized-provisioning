"""Ports — the Protocols the controller's pure domain depends on (docs/03 §4, §5).

A Protocol is a *structural* interface: any class with the right methods satisfies
it, no inheritance required. This is how the controller stays testable — its domain
code depends on these shapes, and a mock or a real web3/pygnmi adapter both fit the
same hole (CLAUDE.md rules 4, 7).
"""

from __future__ import annotations

from typing import Callable, Protocol, runtime_checkable

from .models import ApplyResult, EntitlementView, ResolvedNode, ResolvedPath


@runtime_checkable
class EntitlementReader(Protocol):
    """Read-side of the chain, as the controller sees it (docs/03 §4)."""

    def owner_of(self, entitlement_id: int) -> str: ...

    def get(self, entitlement_id: int) -> EntitlementView: ...

    def chain_time(self) -> int:
        """Latest block.timestamp — the canonical clock (ADR-004)."""
        ...

    def watch_revoked(self, callback: Callable[[int], None]) -> None: ...


@runtime_checkable
class NetworkProvisioner(Protocol):
    """gNMI 'hands' as the controller sees them (docs/03 §5)."""

    def apply_bandwidth(
        self,
        session_id: str,
        path: ResolvedPath,
        capacity_bps: int,
        qos_class: int,
    ) -> ApplyResult: ...

    def apply_telemetry(
        self,
        session_id: str,
        target: ResolvedNode,
        sensor_paths: list[str],
        collector_endpoint: str,
        sample_interval_s: int,
    ) -> ApplyResult: ...

    def teardown(self, session_id: str) -> ApplyResult:
        """MUST be idempotent — calling twice is a success, not an error."""
        ...

    def health(self) -> bool: ...
