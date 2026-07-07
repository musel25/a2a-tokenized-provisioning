"""chainmcp — chain adapter + signing; the only key-holding package (rule 2).

M1.5 ships the client; the MCP server wrapper arrives at M5.4.
"""

from .client import ChainClient, ChainRevert
from .signing import (
    ACTIVATION_PROOF_TEMPLATE,
    OFFER_TYPES,
    activation_proof_message,
    eip712_domain,
    encode_offer,
    offer_digest,
    offer_to_message,
)

__all__ = [
    "ACTIVATION_PROOF_TEMPLATE",
    "ChainClient",
    "ChainRevert",
    "OFFER_TYPES",
    "activation_proof_message",
    "eip712_domain",
    "encode_offer",
    "offer_digest",
    "offer_to_message",
]
