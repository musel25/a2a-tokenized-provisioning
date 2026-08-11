"""The catalogue quarantines per-service knowledge (R12's agent-layer twin of
controller/translators.py): demand extraction, list prices, resource ids, params
codecs. Everything above it must be able to stay service-blind."""

from __future__ import annotations

import eth_abi

from a2a_interfaces.fixtures import (
    BANDWIDTH_NEED,
    BANDWIDTH_PARAMS_ABI,
    RESOURCE_ID,
    TELEMETRY_NEED,
    TELEMETRY_RESOURCE_ID,
)

from agents.catalogue import CATALOGUE, service_for


def test_both_products_are_listed_with_their_chain_enum():
    assert set(CATALOGUE) == {"bandwidth", "telemetry"}
    assert service_for("bandwidth").service_type == 0
    assert service_for("telemetry").service_type == 1


def test_demand_is_bps_for_bandwidth_and_one_slot_for_telemetry():
    assert service_for("bandwidth").demand(BANDWIDTH_NEED) == 50_000_000
    assert service_for("telemetry").demand(TELEMETRY_NEED) == 1


def test_params_encode_exactly_as_the_canonical_fixtures():
    # the catalogue's codec must produce the same bytes the contract tests pin
    assert service_for("bandwidth").encode_params(BANDWIDTH_NEED) == BANDWIDTH_PARAMS_ABI
    expected = "0x" + eth_abi.encode(
        ["string[]", "string", "uint32"],
        [
            TELEMETRY_NEED.sensor_paths,
            TELEMETRY_NEED.collector_endpoint,
            TELEMETRY_NEED.sample_interval_s,
        ],
    ).hex()
    assert service_for("telemetry").encode_params(TELEMETRY_NEED) == expected


def test_list_prices_match_the_deterministic_condition():
    # docs/09: det lifecycles price bandwidth at 10 TOK and telemetry at 8 TOK
    assert service_for("bandwidth").list_price_tok == 10
    assert service_for("telemetry").list_price_tok == 8


def test_resource_ids_are_the_canonical_ones():
    assert service_for("bandwidth").resource_id == RESOURCE_ID
    assert service_for("telemetry").resource_id == TELEMETRY_RESOURCE_ID
