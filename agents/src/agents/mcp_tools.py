"""MCP-backed tool adapters (M5.4): the graphs' stubs become real chain/controller calls.

Same `ConsumerTools`/`ProviderTools` shapes the graphs already depend on — so switching
from stubs to these changes NO graph code (the Protocol seam pays off, exactly as the
controller's ports did). Each adapter holds the callables from a chainmcp instance
(one agent's key) plus, for the consumer, a controller HTTP client.

Uses the in-process `chain_tools` callables rather than a stdio MCP client: the custody
rule is about WHERE the key lives (in chainmcp, this agent's instance), not about the
transport. A stdio server (`build_chain_mcp`) exists for cross-process agents (M5.5+).

Both adapters stamp `last_timings` (seconds, per inner call) the way `LLMClient` stamps
`last_usage` — clocks on the port, nothing different at the port (rule 7), so the
evaluation harness can split phases without reaching inside.
"""

from __future__ import annotations

import secrets
from time import perf_counter

import httpx

from a2a_interfaces import Offer, ServiceNeed, SignedOffer
from a2a_interfaces.fixtures import MOCK_TOK, TERMS_HASH
from chainmcp.mcp_server import chain_tools

from .catalogue import service_for


class ChainConsumerTools:
    """The consumer's tools: fulfill via its own chainmcp, activate via the controller.

    `http` is an injectable httpx client so the same code drives a live controller
    (real server) or an in-process one (Starlette TestClient / ASGITransport) — the
    tests and the evaluation harness use the latter, the `just up` deployment the
    former.
    """

    def __init__(
        self, consumer_chain, controller_url: str, http: httpx.Client | None = None
    ) -> None:
        self._chain = chain_tools(consumer_chain)
        self._controller_url = controller_url.rstrip("/")
        self._http = http or httpx.Client(timeout=10)
        self.last_timings: dict[str, float] = {}
        self.last_tx_hash: str | None = None  # the most recent settle's fulfill tx

    def settle(self, offer: SignedOffer) -> int:
        t0 = perf_counter()
        result = self._chain["fulfill_offer"](offer.model_dump(mode="json"))
        self.last_timings["settle_s"] = perf_counter() - t0
        self.last_tx_hash = result.get("tx_hash")
        return result["entitlement_id"]

    def activate(self, entitlement_id: int, kind: str) -> str:
        """The deliberate three tool calls (docs/03 §6.2): challenge → sign → submit.
        `kind` is the action the consumer intends — the controller's predicate matches
        it against what the entitlement actually grants (E_SCOPE otherwise)."""
        t0 = perf_counter()
        challenge = self._http.post(
            f"{self._controller_url}/v0/challenge", json={"entitlement_id": entitlement_id}
        ).json()
        t1 = perf_counter()
        proof = self._chain["sign_activation_proof"](
            entitlement_id, challenge["nonce"], challenge["controller_id"], challenge["expires_at"]
        )
        t2 = perf_counter()
        response = self._http.post(
            f"{self._controller_url}/v0/activate",
            json={
                "entitlement_id": entitlement_id,
                "action": {"kind": kind},
                "proof": {"nonce": challenge["nonce"], "signature": proof["signature"]},
            },
        )
        activation = response.json()
        t3 = perf_counter()
        self.last_timings.update(  # merge — settle_s from the same lifecycle survives
            challenge_s=t1 - t0, sign_proof_s=t2 - t1, activate_s=t3 - t2
        )
        if "session_id" not in activation:
            raise RuntimeError(f"activation denied: {activation}")
        return activation["session_id"]

    def quote(self, need: ServiceNeed) -> SignedOffer:
        raise NotImplementedError("the consumer gets quotes over A2A (M5.5), not from itself")


class ChainProviderTools:
    """The provider's tool: sign an offer with ITS key via ITS chainmcp instance.

    The offer is built FROM the need and the catalogue — service type, resource,
    params, and window all derive from what was asked; only the price is the judgment
    slot's. A fresh salt per offer keeps otherwise-identical quotes at distinct
    digests (the contract's replay guard burns each digest once)."""

    def __init__(self, provider_chain) -> None:
        self._chain = chain_tools(provider_chain)
        self._provider_address = provider_chain.address
        self.last_timings: dict[str, float] = {}

    def sign_offer(self, need: ServiceNeed, price_tok: int) -> SignedOffer:
        svc = service_for(need.kind)
        t0 = perf_counter()
        offer = Offer(
            provider=self._provider_address,
            consumer="0x" + "0" * 40,  # open offer (v0 default)
            service_type=svc.service_type,
            resource_id=svc.resource_id,
            params=svc.encode_params(need),
            start_time=need.window.start,
            end_time=need.window.end,
            payment_token=MOCK_TOK,
            price=str(price_tok * 10**18),
            valid_until=need.window.end,  # quote good through the service window (v0 simplicity)
            salt="0x" + secrets.token_hex(32),
            terms_hash=TERMS_HASH,
        )
        signed = SignedOffer.model_validate(self._chain["sign_offer"](offer.model_dump(mode="json")))
        self.last_timings = {"sign_offer_s": perf_counter() - t0}
        return signed
