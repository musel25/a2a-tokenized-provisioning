"""The cross-stack signature tests — the single most failure-prone seam (docs/01 M1.5).

Python builds and signs the EIP-712 offer; Solidity's `fulfill` verifies it, on a live
Anvil. When these are green, story chapters 4 and 5 are physically true: two languages,
one byte-identical hash. Nothing but a live-chain test can catch a domain or field-order
divergence — unit tests on either side would each agree with themselves.
"""

from __future__ import annotations

import time

from a2a_interfaces import EntitlementReader
from a2a_interfaces.fixtures import (
    ADA,
    BELL,
    CANONICAL_OFFER,
    CAPACITY_50_MBPS,
    PRICE_10_TOK,
    QOS_CLASS,
    TERMS_DOC,
)
import pytest

from chainmcp import ChainRevert
from chainmcp.testing import anvil_available, artifacts_available

pytestmark = pytest.mark.skipif(
    not (anvil_available() and artifacts_available()),
    reason="needs anvil on PATH and forge-built artifacts in contracts/out/",
)

PRICE = int(PRICE_10_TOK)


def test_python_digest_equals_contract_hashOffer(ada):
    """The two hash implementations agree bit-for-bit — the seam, isolated."""
    contract_digest = ada._settlement.functions.hashOffer(ada._offer_tuple(CANONICAL_OFFER)).call()
    assert ada.offer_digest(CANONICAL_OFFER) == contract_digest


def test_python_signs_solidity_verifies(ada, bell):
    """The headline: Bell signs in Python, the CONTRACT accepts, ticket mints to Ada."""
    ada.faucet(PRICE * 10)
    signed = bell.sign_offer(CANONICAL_OFFER, terms_doc=TERMS_DOC)

    tx_hash, entitlement_id = ada.approve_and_fulfill(signed)

    assert ada.owner_of(entitlement_id) == ADA
    assert ada.tok_balance(BELL) == PRICE
    assert ada.offer_consumed(CANONICAL_OFFER) is True
    view = ada.get(entitlement_id)
    assert view.issuer == BELL
    assert view.params.capacity_bps == CAPACITY_50_MBPS
    assert view.params.qos_class == QOS_CLASS
    assert view.start_time == CANONICAL_OFFER.start_time
    assert view.revoked is False


def test_replay_raises_the_contracts_error_name(ada, bell):
    ada.faucet(PRICE * 10)
    signed = bell.sign_offer(CANONICAL_OFFER)
    ada.approve_and_fulfill(signed)
    try:
        ada.approve_and_fulfill(signed)
        raise AssertionError("replay should revert")
    except ChainRevert as err:
        assert err.name == "OfferAlreadyUsed"


def test_tampered_offer_dies_as_BadSignature(ada, bell):
    """One field changed after signing → the contract sees a stranger's signature."""
    ada.faucet(PRICE * 10)
    signed = bell.sign_offer(CANONICAL_OFFER)
    cheaper = signed.offer.model_copy(update={"price": str(PRICE // 10)})
    tampered = signed.model_copy(update={"offer": cheaper})
    try:
        ada.approve_and_fulfill(tampered)
        raise AssertionError("tampered offer should revert")
    except ChainRevert as err:
        assert err.name == "BadSignature"


def test_client_satisfies_the_reader_port(ada):
    """Rule 7: the real adapter fits the same hole as FakeChain."""
    assert isinstance(ada, EntitlementReader)


def test_owner_of_unknown_id_raises_KeyError_like_the_fake(ada):
    try:
        ada.owner_of(999)
        raise AssertionError("unknown id should raise")
    except KeyError:
        pass


def test_chain_time_is_block_timestamp_and_advances(ada, anvil):
    before = ada.chain_time()
    anvil.increase_time(ada._w3, 3600)
    assert ada.chain_time() >= before + 3600


def test_watch_revoked_delivers_the_event(ada, bell):
    """Bell revokes on-chain; the polling watcher hands the id to the callback."""
    ada.faucet(PRICE * 10)
    _, entitlement_id = ada.approve_and_fulfill(bell.sign_offer(CANONICAL_OFFER))

    seen: list[int] = []
    ada.watch_revoked(seen.append)
    time.sleep(0.3)  # let the watcher record its starting block
    bell.revoke(entitlement_id)

    deadline = time.monotonic() + 5
    while not seen and time.monotonic() < deadline:
        time.sleep(0.05)
    assert seen == [entitlement_id]
    assert ada.get(entitlement_id).revoked is True


def test_revoke_by_non_issuer_raises_NotIssuer(ada, bell):
    ada.faucet(PRICE * 10)
    _, entitlement_id = ada.approve_and_fulfill(bell.sign_offer(CANONICAL_OFFER))
    try:
        ada.revoke(entitlement_id)  # Ada owns it but did not issue it
        raise AssertionError("owner revoke should revert")
    except ChainRevert as err:
        assert err.name == "NotIssuer"


def test_activation_proof_recovers_to_signer(ada):
    from eth_account import Account
    from eth_account.messages import encode_defunct

    signature, address = ada.sign_activation_proof(7, "0xabcd", "bw-ctrl-1", 1757945100)
    message = encode_defunct(text="a2a-activate|bw-ctrl-1|0xabcd|7|1757945100")
    assert Account.recover_message(message, signature=signature) == address == ADA


def test_targeted_offer_crosses_the_seam(ada, bell):
    """Consumer binding, Python-signed end to end: the wrong buyer is refused by the
    CONTRACT, the named buyer sails through with the identical signature."""
    ada.faucet(PRICE * 10)
    bound = CANONICAL_OFFER.model_copy(update={"consumer": ADA})
    signed = bell.sign_offer(bound)

    try:
        # Bell needn't even be funded: consumer binding refuses before the funds pull.
        bell.approve_and_fulfill(signed)
        raise AssertionError("wrong buyer should revert")
    except ChainRevert as err:
        assert err.name == "WrongConsumer"

    _, entitlement_id = ada.approve_and_fulfill(signed)
    assert ada.owner_of(entitlement_id) == ADA


def test_telemetry_params_decode_roundtrip(ada, bell):
    """serviceType 1 crosses the seam too: Python-encoded telemetry params mint on-chain
    and decode back into a TelemetryParams view (docs/03 §4.2 row 2)."""
    import eth_abi

    from a2a_interfaces.fixtures import TELEMETRY_NEED

    blob = eth_abi.encode(
        ["string[]", "string", "uint32"],
        [
            TELEMETRY_NEED.sensor_paths,
            TELEMETRY_NEED.collector_endpoint,
            TELEMETRY_NEED.sample_interval_s,
        ],
    )
    offer = CANONICAL_OFFER.model_copy(
        update={
            "service_type": 1,
            "params": "0x" + blob.hex(),
            "salt": "0x" + f"{0x7E1E:064x}",
        }
    )
    ada.faucet(PRICE * 10)
    _, entitlement_id = ada.approve_and_fulfill(bell.sign_offer(offer))

    view = ada.get(entitlement_id)
    assert view.params.sensor_paths == TELEMETRY_NEED.sensor_paths
    assert view.params.collector_endpoint == TELEMETRY_NEED.collector_endpoint
    assert view.params.sample_interval_s == TELEMETRY_NEED.sample_interval_s


def test_get_unknown_id_raises_KeyError_like_the_fake(ada):
    """get(), not just owner_of: the existence gate keeps dict semantics at the port."""
    try:
        ada.get(999)
        raise AssertionError("unknown id should raise")
    except KeyError:
        pass


def test_get_unknown_service_type_is_a_named_refusal(ada, bell):
    """The contract mints ANY signed serviceType; the reader must refuse unknown ones
    with a clear error, not a raw eth-abi crash mid-decode."""
    offer = CANONICAL_OFFER.model_copy(update={"service_type": 2, "salt": "0x" + f"{0xBAD:064x}"})
    ada.faucet(PRICE * 10)
    _, entitlement_id = ada.approve_and_fulfill(bell.sign_offer(offer))
    try:
        ada.get(entitlement_id)
        raise AssertionError("serviceType 2 should be refused by the decoder")
    except ValueError as err:
        assert "serviceType 2" in str(err)


def test_rejected_fulfill_withdraws_the_allowance(ada, bell):
    """The approve is a separate mined tx, outside the contract's I3 rollback — the
    client itself must clean it up so a refused purchase leaves no standing approval."""
    ada.faucet(PRICE * 10)
    signed = bell.sign_offer(CANONICAL_OFFER)
    ada.approve_and_fulfill(signed)
    try:
        ada.approve_and_fulfill(signed)  # replay → OfferAlreadyUsed
    except ChainRevert:
        pass
    allowance = ada._tok.functions.allowance(ADA, ada._settlement.address).call()
    assert allowance == 0


def test_watch_after_close_raises(ada):
    ada.watch_revoked(lambda _id: None)
    ada.close()
    try:
        ada.watch_revoked(lambda _id: None)
        raise AssertionError("watching a closed client should raise")
    except RuntimeError:
        pass
