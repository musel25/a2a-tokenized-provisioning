"""M5.5 — A2A: cards, the wire round-trip, and the end-to-end integrity demo.

The headline (docs/01 M5.5): a quote travels over the wire; tampering one offer field in
transit → M1.3's `BadSignature` catches it. That the SDK is confined to a2a_adapter.py
is checked structurally. The Anvil leg (tamper → BadSignature) skips without artifacts."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from a2a_interfaces import Decline, SignedOffer
from a2a_interfaces.fixtures import BANDWIDTH_NEED, CANONICAL_SIGNED_OFFER

from agents.a2a_adapter import (
    decode_need,
    decode_offer_or_decline,
    encode_need,
    encode_offer_or_decline,
    provider_card,
)


def test_provider_card_has_the_quote_skill():
    card = provider_card("bandwidth-provider", "http://localhost:9101/", "bandwidth")
    assert card.url == "http://localhost:9101/"
    assert [s.id for s in card.skills] == ["quote_bandwidth"]


def test_need_round_trips_over_the_wire():
    payload = encode_need(BANDWIDTH_NEED)
    assert decode_need(payload) == BANDWIDTH_NEED


def test_offer_and_decline_round_trip():
    assert decode_offer_or_decline(encode_offer_or_decline(CANONICAL_SIGNED_OFFER)) == (
        CANONICAL_SIGNED_OFFER
    )
    decline = Decline(reason="no capacity")
    assert decode_offer_or_decline(encode_offer_or_decline(decline)) == decline


def test_a2a_sdk_import_is_confined_to_the_adapter():
    """ADR-002, executable: only a2a_adapter.py may import the a2a SDK."""
    agents_src = Path(__file__).parents[1] / "src" / "agents"
    offenders = []
    for py in agents_src.glob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            mods = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            if any(m.split(".")[0] == "a2a" for m in mods) and py.name != "a2a_adapter.py":
                offenders.append(py.name)
    assert not offenders, f"a2a SDK imported outside a2a_adapter.py: {offenders}"


# --- the integrity demo: a tampered offer in transit dies as BadSignature -------------

from chainmcp.testing import anvil_available, artifacts_available, launch_anvil, ANVIL_KEYS  # noqa: E402

_chain = pytest.mark.skipif(
    not (anvil_available() and artifacts_available()), reason="needs Anvil + artifacts"
)


@_chain
def test_tampering_in_transit_is_caught_by_the_contract():
    from chainmcp import ChainClient, ChainRevert

    anvil = launch_anvil(timestamp=1757944800 - 1680)
    bell = ChainClient(anvil.rpc_url, ANVIL_KEYS["bell"], deployment=anvil.deployment)
    ada = ChainClient(anvil.rpc_url, ANVIL_KEYS["ada"], deployment=anvil.deployment)
    try:
        ada.faucet(100 * 10**18)
        # Bell signs and sends the offer over the (simulated) A2A wire.
        signed = bell.sign_offer(CANONICAL_SIGNED_OFFER.offer)
        on_the_wire = encode_offer_or_decline(signed)

        # A man-in-the-middle rewrites the price to 1 TOK before it reaches Ada.
        import json

        blob = json.loads(on_the_wire)
        blob["offer"]["price"] = str(10**18)
        tampered = decode_offer_or_decline(json.dumps(blob))
        assert isinstance(tampered, SignedOffer)

        # Ada tries to redeem it — the contract recovers a stranger, not Bell.
        try:
            ada.approve_and_fulfill(tampered)
            raise AssertionError("tampered offer should not mint")
        except ChainRevert as err:
            assert err.name == "BadSignature"
    finally:
        bell.close()
        ada.close()
        anvil.stop()
