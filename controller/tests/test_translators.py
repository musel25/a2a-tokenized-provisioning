"""M4.3 — translators, pinned by golden files: fixture entitlement in → EXACT call
list out. The goldens under tests/goldens/ were reviewed by eye once (that review IS
the point); any drift is a red test explaining itself as a diff."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from a2a_interfaces.fixtures import (
    CANONICAL_ENTITLEMENT_VIEW,
    TELEMETRY_ENTITLEMENT_VIEW,
)

from controller.resource_map import load_resource_map
from controller.translators import ProvisionerCall, UnmappedResource, translate

GOLDENS = Path(__file__).parent / "goldens"
RESOURCE_MAP = load_resource_map()  # the checked-in canonical map


def _as_jsonable(calls: list[ProvisionerCall]) -> list[dict]:
    """Golden form: dataclass → dict, pydantic values → plain data."""
    out = []
    for call in calls:
        kwargs = {
            key: value.model_dump() if hasattr(value, "model_dump") else value
            for key, value in call.kwargs.items()
        }
        out.append({"method": call.method, "kwargs": kwargs})
    return out


@pytest.mark.parametrize(
    ("view", "golden_name"),
    [
        (CANONICAL_ENTITLEMENT_VIEW, "bandwidth_ticket7.json"),
        (TELEMETRY_ENTITLEMENT_VIEW, "telemetry_ticket8.json"),
    ],
    ids=["bandwidth", "telemetry"],
)
def test_translation_matches_golden(view, golden_name):
    calls = translate("ent%d-a1" % view.id, view, RESOURCE_MAP)
    golden = json.loads((GOLDENS / golden_name).read_text())
    assert _as_jsonable(calls) == golden


def test_unmapped_resource_raises_for_the_wiring_to_map():
    stranger = CANONICAL_ENTITLEMENT_VIEW.model_copy(update={"resource_id": b"\x99" * 32})
    with pytest.raises(UnmappedResource):
        translate("s", stranger, RESOURCE_MAP)


def test_calls_are_data_not_behavior():
    # The wiring applies these with getattr(provisioner, method)(**kwargs) — so the
    # method names must be exactly the NetworkProvisioner port's (docs/03 §5).
    from a2a_interfaces import NetworkProvisioner

    for view in (CANONICAL_ENTITLEMENT_VIEW, TELEMETRY_ENTITLEMENT_VIEW):
        for call in translate("s", view, RESOURCE_MAP):
            assert dataclasses.is_dataclass(call)
            assert callable(getattr(NetworkProvisioner, call.method, None)), call.method


def test_resource_map_loader_rejects_unknown_kind(tmp_path):
    bad = tmp_path / "map.yaml"
    bad.write_text('"0x07":\n  kind: teleporter\n  device: srl1\n')
    with pytest.raises(ValueError, match="teleporter"):
        load_resource_map(bad)