"""The canonical fixtures carry the story's exact numbers."""

from a2a_interfaces import fixtures


def test_story_numbers_are_canonical():
    assert fixtures.CAPACITY_50_MBPS == 50_000_000
    assert fixtures.PRICE_10_TOK == "10000000000000000000"  # 10 TOK, 18 decimals
    assert fixtures.TICKET_ID == 7
    assert fixtures.ADA.lower().startswith("0xf39fd6")  # anvil account 0
    assert fixtures.BELL.lower().startswith("0x709979")  # anvil account 1


def test_canonical_offer_is_open_and_from_bell():
    assert fixtures.CANONICAL_OFFER.consumer == fixtures.ZERO_ADDRESS  # open offer (§1.2)
    assert fixtures.CANONICAL_OFFER.provider == fixtures.BELL


def test_bandwidth_params_abi_encodes_capacity_and_qos():
    blob = fixtures.BANDWIDTH_PARAMS_ABI[2:]
    assert len(blob) == 128  # two 32-byte words
    assert int(blob[:64], 16) == fixtures.CAPACITY_50_MBPS
    assert int(blob[64:], 16) == fixtures.QOS_CLASS


def test_entitlement_view_resource_id_is_32_bytes():
    assert len(fixtures.CANONICAL_ENTITLEMENT_VIEW.resource_id) == 32
    assert fixtures.CANONICAL_ENTITLEMENT_VIEW.issuer == fixtures.BELL
