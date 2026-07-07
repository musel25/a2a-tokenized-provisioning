"""EIP-712 / EIP-191 message building — the Python half of the signature seam.

Everything here must match `contracts/src/Settlement.sol` BYTE-FOR-BYTE: the domain
(docs/03 §2.1), the type string, the field order, and the dynamic-type hashing rule.
One divergent byte and every signature recovers to a stranger (`BadSignature`). The
cross-stack tests in `chainmcp/tests/` exist to catch exactly that class of bug —
nothing else can.

This module builds and hashes messages; it never touches a key. Key custody is
`ChainClient`'s (rule 2).
"""

from __future__ import annotations

from eth_account.messages import SignableMessage, encode_typed_data
from eth_utils import keccak

from a2a_interfaces import Offer

# The twelve Offer fields, in struct order — the Python twin of OFFER_TYPEHASH's type
# string. eth-account derives the typehash from this dict, so field ORDER here is as
# load-bearing as it is in Solidity.
OFFER_TYPES = {
    "Offer": [
        {"name": "provider", "type": "address"},
        {"name": "consumer", "type": "address"},
        {"name": "serviceType", "type": "uint8"},
        {"name": "resourceId", "type": "bytes32"},
        {"name": "params", "type": "bytes"},
        {"name": "startTime", "type": "uint64"},
        {"name": "endTime", "type": "uint64"},
        {"name": "paymentToken", "type": "address"},
        {"name": "price", "type": "uint256"},
        {"name": "validUntil", "type": "uint64"},
        {"name": "salt", "type": "bytes32"},
        {"name": "termsHash", "type": "bytes32"},
    ]
}

# The activation-proof template (docs/03 §3.2): EIP-191 personal_sign, not EIP-712 —
# the controller verifies it in Python with Account.recover_message, no contract involved.
ACTIVATION_PROOF_TEMPLATE = "a2a-activate|{controller_id}|{nonce}|{entitlement_id}|{expires_at}"


def eip712_domain(chain_id: int, settlement: str) -> dict:
    """The pinned domain (docs/03 §2.1). name/version are constants of the protocol."""
    return {
        "name": "A2AProvisioning",
        "version": "0",
        "chainId": chain_id,
        "verifyingContract": settlement,
    }


def offer_to_message(offer: Offer) -> dict:
    """Offer (wire shape: hex strings, decimal-string price) → typed-data message values.

    eth-account wants machine types: ints for uints, raw bytes for bytes/bytes32.
    The camelCase keys come from the model's aliases — the same names the contract's
    type string uses.
    """
    wire = offer.model_dump(by_alias=True)
    for key in ("resourceId", "params", "salt", "termsHash"):
        wire[key] = bytes.fromhex(wire[key][2:])
    wire["price"] = int(wire["price"])
    return wire


def encode_offer(offer: Offer, chain_id: int, settlement: str) -> SignableMessage:
    """The exact bytes the provider signs: (domain separator, struct hash) per EIP-712."""
    return encode_typed_data(
        domain_data=eip712_domain(chain_id, settlement),
        message_types=OFFER_TYPES,
        message_data=offer_to_message(offer),
    )


def offer_digest(offer: Offer, chain_id: int, settlement: str) -> bytes:
    """The 32-byte EIP-712 digest — must equal the contract's `hashOffer(offer)`.

    EIP-712's final digest is keccak(0x19 ‖ 0x01 ‖ domainSeparator ‖ structHash);
    SignableMessage carries those last two as header/body.
    """
    signable = encode_offer(offer, chain_id, settlement)
    return keccak(b"\x19" + signable.version + signable.header + signable.body)


def activation_proof_message(
    controller_id: str, nonce: str, entitlement_id: int, expires_at: int
) -> str:
    return ACTIVATION_PROOF_TEMPLATE.format(
        controller_id=controller_id,
        nonce=nonce,
        entitlement_id=entitlement_id,
        expires_at=expires_at,
    )
