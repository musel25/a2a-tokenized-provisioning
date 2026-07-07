"""Round-trip: model -> JSON -> model is identity for every boundary shape."""

from pydantic import TypeAdapter

from a2a_interfaces import (
    DecisionOutput,
    EntitlementView,
    Offer,
    ServiceNeed,
    SignedOffer,
    fixtures,
)

_ServiceNeed = TypeAdapter(ServiceNeed)


def test_offer_roundtrips_as_camelcase_json():
    offer = fixtures.CANONICAL_OFFER
    blob = offer.model_dump_json(by_alias=True)
    # the Offer mirrors the Solidity struct -> camelCase on the wire
    assert '"serviceType"' in blob
    assert '"resourceId"' in blob
    assert Offer.model_validate_json(blob) == offer


def test_signed_offer_roundtrips():
    signed = fixtures.CANONICAL_SIGNED_OFFER
    assert SignedOffer.model_validate_json(signed.model_dump_json(by_alias=True)) == signed


def test_bandwidth_need_roundtrips_as_snakecase_json():
    need = fixtures.BANDWIDTH_NEED
    blob = _ServiceNeed.dump_json(need)
    assert b'"capacity_bps"' in blob  # A2A payloads stay snake_case
    assert _ServiceNeed.validate_json(blob) == need


def test_telemetry_need_roundtrips_and_picks_variant_by_kind():
    need = fixtures.TELEMETRY_NEED
    restored = _ServiceNeed.validate_json(_ServiceNeed.dump_json(need))
    assert restored == need
    assert restored.kind == "telemetry"


def test_entitlement_view_roundtrips_with_bytes_as_hex():
    view = fixtures.CANONICAL_ENTITLEMENT_VIEW
    assert EntitlementView.model_validate_json(view.model_dump_json()) == view


def test_decision_output_roundtrips():
    decision = fixtures.DECISION_ACCEPT
    assert DecisionOutput.model_validate_json(decision.model_dump_json()) == decision


def test_telemetry_sample_roundtrips():
    from a2a_interfaces import TelemetrySample

    sample = TelemetrySample(
        session_id="ent7-a1",
        path="srl_nokia-interfaces:interface[name=ethernet-1/1]/statistics",
        timestamp_ns=1783394038730008273,
        values={"statistics": {"in-octets": "832824572"}},
    )
    again = TelemetrySample.model_validate_json(sample.model_dump_json())
    assert again == sample
    assert again.v == 0
