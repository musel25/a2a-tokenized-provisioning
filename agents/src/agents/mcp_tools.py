"""MCP-backed tool adapters (M5.4): the graphs' stubs become real chain/controller calls.

Same `ConsumerTools`/`ProviderTools` shapes the graphs already depend on — so switching
from stubs to these changes NO graph code (the Protocol seam pays off, exactly as the
controller's ports did). Each adapter holds the callables from a chainmcp instance
(one agent's key) plus, for the consumer, a controller HTTP client.

Uses the in-process `chain_tools` callables rather than a stdio MCP client: the custody
rule is about WHERE the key lives (in chainmcp, this agent's instance), not about the
transport. A stdio server (`build_chain_mcp`) exists for cross-process agents (M5.5+).
"""

from __future__ import annotations

import httpx

from a2a_interfaces import BandwidthNeed, Offer, ServiceNeed, SignedOffer
from a2a_interfaces.fixtures import (
    CAPACITY_50_MBPS,
    MOCK_TOK,
    QOS_CLASS,
    RESOURCE_ID,
    SALT,
    TERMS_HASH,
    WINDOW,
)
from chainmcp.mcp_server import chain_tools


class ChainConsumerTools:
    """The consumer's tools: fulfill via its own chainmcp, activate via the controller."""

    def __init__(self, consumer_chain, controller_url: str) -> None:
        self._chain = chain_tools(consumer_chain)
        self._client = consumer_chain  # for the activation proof (needs the key)
        self._controller_url = controller_url

    def settle(self, offer: SignedOffer) -> int:
        return self._chain["fulfill_offer"](offer.model_dump(mode="json"))["entitlement_id"]

    def activate(self, entitlement_id: int) -> str:
        """The deliberate three tool calls (docs/03 §6.2): challenge → sign → submit."""
        challenge = httpx.post(
            f"{self._controller_url}/v0/challenge",
            json={"entitlement_id": entitlement_id},
            timeout=10,
        ).json()
        proof = self._chain["sign_activation_proof"](
            entitlement_id, challenge["nonce"], challenge["controller_id"], challenge["expires_at"]
        )
        activation = httpx.post(
            f"{self._controller_url}/v0/activate",
            json={
                "entitlement_id": entitlement_id,
                "action": {"kind": "bandwidth"},
                "proof": {"nonce": challenge["nonce"], "signature": proof["signature"]},
            },
            timeout=10,
        ).json()
        return activation["session_id"]

    def quote(self, need: ServiceNeed) -> SignedOffer:
        raise NotImplementedError("the consumer gets quotes over A2A (M5.5), not from itself")


class ChainProviderTools:
    """The provider's tool: sign an offer with ITS key via ITS chainmcp instance."""

    def __init__(self, provider_chain) -> None:
        self._chain = chain_tools(provider_chain)
        self._provider_address = provider_chain.address

    def sign_offer(self, need: BandwidthNeed, price_tok: int) -> SignedOffer:
        offer = Offer(
            provider=self._provider_address,
            consumer="0x" + "0" * 40,  # open offer (v0 default)
            service_type=0,
            resource_id=RESOURCE_ID,
            params="0x" + f"{CAPACITY_50_MBPS:064x}" + f"{QOS_CLASS:064x}",
            start_time=WINDOW.start,
            end_time=WINDOW.end,
            payment_token=MOCK_TOK,
            price=str(price_tok * 10**18),
            valid_until=WINDOW.end,  # quote good through the service window (v0 simplicity)
            salt=SALT,
            terms_hash=TERMS_HASH,
        )
        return SignedOffer.model_validate(self._chain["sign_offer"](offer.model_dump(mode="json")))
