"""Rejection: the border refuses malformed data instead of letting it propagate."""

import pytest
from pydantic import TypeAdapter, ValidationError

from a2a_interfaces import BandwidthNeed, DecisionOutput, Offer, ServiceNeed, fixtures

_ServiceNeed = TypeAdapter(ServiceNeed)


def test_negative_capacity_rejected():
    with pytest.raises(ValidationError):
        BandwidthNeed(
            src="hostA", dst="hostB", capacity_bps=-1, qos_class=1, window=fixtures.WINDOW
        )


def test_unknown_kind_rejected():
    with pytest.raises(ValidationError):
        _ServiceNeed.validate_python({"v": 0, "kind": "laser", "window": {"start": 1, "end": 2}})


def test_malformed_address_rejected():
    bad = fixtures.CANONICAL_OFFER.model_dump(by_alias=True)
    bad["provider"] = "0xnothex"
    with pytest.raises(ValidationError):
        Offer.model_validate(bad)


def test_qos_class_above_uint8_rejected():
    with pytest.raises(ValidationError):
        BandwidthNeed(
            src="hostA", dst="hostB", capacity_bps=1, qos_class=256, window=fixtures.WINDOW
        )


def test_float_price_rejected():
    bad = fixtures.CANONICAL_OFFER.model_dump(by_alias=True)
    bad["price"] = "10.5"  # decimal strings are integers only (§0: no floats)
    with pytest.raises(ValidationError):
        Offer.model_validate(bad)


def test_unknown_field_forbidden():
    with pytest.raises(ValidationError):
        DecisionOutput(accept=True, reason="ok", bogus="nope")


def test_frozen_models_are_immutable():
    with pytest.raises(ValidationError):
        fixtures.CANONICAL_OFFER.price = "1"
