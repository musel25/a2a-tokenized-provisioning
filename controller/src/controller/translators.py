"""Translators (docs/05 §5): an entitlement's terms → the exact provisioner calls.

Pure functions, one per serviceType. The controller's ONLY knowledge of topology is
the resource map passed in (ADR-005: `resource_map.yaml`, loaded at the edge by
`resource_map.py`); netctl's only knowledge of the deal is what these calls carry.
Golden-file tests pin the exact output — reviewed by eye once, guarded forever.
"""

from __future__ import annotations

from dataclasses import dataclass

from a2a_interfaces import EntitlementView, ResolvedNode, ResolvedPath


@dataclass(frozen=True)
class ProvisionerCall:
    """One intended NetworkProvisioner invocation, as data — kept controller-local
    on purpose (rule 9: nobody else needs it; the wiring applies it with getattr)."""

    method: str
    kwargs: dict


class UnmappedResource(Exception):
    """The entitlement references a resource this controller doesn't manage — the
    wiring surfaces it as E_SCOPE (docs/05 §5): valid ticket, wrong venue."""

    def __init__(self, resource_id: bytes) -> None:
        super().__init__("0x" + resource_id.hex())
        self.resource_id = resource_id


def translate(
    session_id: str,
    view: EntitlementView,
    resource_map: dict[bytes, ResolvedPath | ResolvedNode],
) -> list[ProvisionerCall]:
    """Dispatch on serviceType. The predicate already guaranteed the type is known
    (E_SCOPE otherwise), so an unknown type HERE is a programming error, not a denial."""
    resolved = resource_map.get(view.resource_id)
    if resolved is None:
        raise UnmappedResource(view.resource_id)
    if view.service_type == 0:
        return _bandwidth(session_id, view, resolved)
    if view.service_type == 1:
        return _telemetry(session_id, view, resolved)
    raise AssertionError(f"predicate admitted unknown serviceType {view.service_type}")


def _bandwidth(session_id: str, view: EntitlementView, path: ResolvedPath) -> list[ProvisionerCall]:
    return [
        ProvisionerCall(
            method="apply_bandwidth",
            kwargs={
                "session_id": session_id,
                "path": path,
                "capacity_bps": view.params.capacity_bps,
                "qos_class": view.params.qos_class,
            },
        )
    ]


def _telemetry(session_id: str, view: EntitlementView, node: ResolvedNode) -> list[ProvisionerCall]:
    return [
        ProvisionerCall(
            method="apply_telemetry",
            kwargs={
                "session_id": session_id,
                "target": node,
                "sensor_paths": view.params.sensor_paths,
                "collector_endpoint": view.params.collector_endpoint,
                "sample_interval_s": view.params.sample_interval_s,
            },
        )
    ]
