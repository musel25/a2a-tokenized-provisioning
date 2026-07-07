"""Pure signing tests — no chain, no keys leaving the module.

The cross-stack HALF of the seam (Python vs the live contract) is in
test_cross_stack.py; these pin the Python-side building blocks in isolation.
"""

from __future__ import annotations

from eth_account import Account
from eth_utils import keccak

from a2a_interfaces.fixtures import BELL, CANONICAL_OFFER
from chainmcp import activation_proof_message, encode_offer, offer_to_message
from chainmcp.testing import ANVIL_KEYS

SETTLEMENT = "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512"  # any address works off-chain


def test_offer_message_uses_contract_field_names_and_machine_types():
    message = offer_to_message(CANONICAL_OFFER)
    # camelCase keys — the exact names in the Solidity type string
    assert set(message) == {
        "provider",
        "consumer",
        "serviceType",
        "resourceId",
        "params",
        "startTime",
        "endTime",
        "paymentToken",
        "price",
        "validUntil",
        "salt",
        "termsHash",
    }
    assert isinstance(message["price"], int)  # decimal string → int for hashing
    assert message["price"] == 10 * 10**18
    assert isinstance(message["resourceId"], bytes) and len(message["resourceId"]) == 32
    assert isinstance(message["params"], bytes) and len(message["params"]) == 64


def test_typehash_matches_contract_constant():
    """keccak of the type string == the OFFER_TYPEHASH pinned in Settlement.sol.

    The constant on the right was read off the deployed contract in the M1.3 lab
    (EXPLORE-fulfill.md §2) — an external witness, not a copy of our own math.
    """
    type_string = (
        "Offer(address provider,address consumer,uint8 serviceType,bytes32 resourceId,"
        "bytes params,uint64 startTime,uint64 endTime,address paymentToken,uint256 price,"
        "uint64 validUntil,bytes32 salt,bytes32 termsHash)"
    )
    assert (
        keccak(text=type_string).hex()
        == "14da67f04d1d4e3c5800536c542a24924372ff20a8872c71ad7d89086bd71e6d"
    )
    # and eth-account derives the same struct hashing from OFFER_TYPES: proven end-to-end
    # against the live contract in test_cross_stack.py.


def test_signature_recovers_to_bell():
    """Sign here, recover here: the round trip that must also hold on-chain."""
    signable = encode_offer(CANONICAL_OFFER, chain_id=31337, settlement=SETTLEMENT)
    signed = Account.sign_message(signable, ANVIL_KEYS["bell"])
    assert Account.recover_message(signable, signature=signed.signature) == BELL


def test_activation_proof_string_matches_docs03():
    assert (
        activation_proof_message("bw-ctrl-1", "0xabcd", 7, 1757945100)
        == "a2a-activate|bw-ctrl-1|0xabcd|7|1757945100"
    )
