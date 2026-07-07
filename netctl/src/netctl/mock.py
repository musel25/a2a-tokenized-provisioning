"""MockProvisioner — the recording double for the gNMI hands.

Born as the skeleton's FakeNet (M0.3), promoted here at M3.2 so the mock and the
real adapter live side by side and run the SAME contract suite (rule 7:
netctl/tests/test_provisioner_contract.py). e2e's `FakeNet` is now an alias.

It records instead of provisioning: `applied[session_id]` holds what a router would
have been told; `torn_down` remembers every teardown. Tests assert against those.
"""

from __future__ import annotations

from a2a_interfaces import ApplyResult, ResolvedNode, ResolvedPath


class MockProvisioner:
    """Satisfies NetworkProvisioner (docs/03 §5) by remembering, not doing."""

    def __init__(self) -> None:
        self.applied: dict[str, dict] = {}
        self.torn_down: list[str] = []

    def apply_bandwidth(
        self,
        session_id: str,
        path: ResolvedPath,
        capacity_bps: int,
        qos_class: int,
    ) -> ApplyResult:
        self.applied[session_id] = {
            "path": path,
            "capacity_bps": capacity_bps,
            "qos_class": qos_class,
        }
        return ApplyResult(ok=True)

    def apply_telemetry(
        self,
        session_id: str,
        target: ResolvedNode,
        sensor_paths: list[str],
        collector_endpoint: str,
        sample_interval_s: int,
    ) -> ApplyResult:
        raise NotImplementedError("telemetry lands at M3.3 (ADR-007)")

    def teardown(self, session_id: str) -> ApplyResult:
        # Idempotent (rule 8): pop with default, never raise on a second call.
        self.applied.pop(session_id, None)
        self.torn_down.append(session_id)
        return ApplyResult(ok=True)

    def health(self) -> bool:
        return True
