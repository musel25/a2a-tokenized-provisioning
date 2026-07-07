"""M5.4 acceptance: an agent-driven purchase mints on Anvil END TO END VIA TOOLS.

Bell's provider graph signs through Bell's chainmcp; Ada's consumer settles through
Ada's chainmcp; the entitlement mints on a live Anvil. The keys never leave their
chainmcp instances (rule 2) — the graphs only ever hold tool callables.

Needs Anvil + forge artifacts; skips otherwise (no LLM needed — the decision/quote
slots are stubbed, as in M5.2/M5.3; this milestone is about the TOOLS, not judgment)."""

from __future__ import annotations

import pytest

from a2a_interfaces import SignedOffer
from chainmcp import ChainClient
from chainmcp.testing import ANVIL_KEYS, anvil_available, artifacts_available, launch_anvil

from agents.mcp_tools import ChainConsumerTools, ChainProviderTools
from agents.provider_graph import CapacityLedger, ProviderState, QuoteDecision, build_provider_graph

from tests_support import bandwidth_need_for

pytestmark = pytest.mark.skipif(
    not (anvil_available() and artifacts_available()),
    reason="needs Anvil + forge artifacts",
)

STORY_TIME = 1757944800 - 1680  # 13:32, before the window (offers valid)


class _StubLLM:
    def __init__(self, decision):
        self._d = decision

    def structured(self, *a):
        return self._d


@pytest.fixture()
def anvil():
    chain = launch_anvil(timestamp=STORY_TIME)
    yield chain
    chain.stop()


def test_agent_buys_via_tools_mints_on_anvil(anvil):
    bell = ChainClient(anvil.rpc_url, ANVIL_KEYS["bell"], deployment=anvil.deployment)
    ada = ChainClient(anvil.rpc_url, ANVIL_KEYS["ada"], deployment=anvil.deployment)
    try:
        ada.faucet(100 * 10**18)  # buying money

        # Provider graph: admission (deterministic) + a stubbed 10-TOK quote, SIGNED via
        # Bell's chainmcp tool.
        provider_graph = build_provider_graph(
            _StubLLM(QuoteDecision(quote=True, price_tok=10, reason="fair")),
            ChainProviderTools(bell),
            CapacityLedger(capacity_bps=100_000_000),
        )
        need = bandwidth_need_for(50_000_000)
        offer = provider_graph.invoke(ProviderState(need=need))["result"]
        assert isinstance(offer, SignedOffer)
        assert offer.offer.provider == bell.address

        # Consumer graph: a stubbed accept, then SETTLE via Ada's chainmcp tool —
        # the mint happens on Anvil, through tools, keys never seen by the graph.
        consumer_tools = ChainConsumerTools(ada, controller_url="http://unused")
        # (the full graph incl. activate against a live controller is M5.6; here we
        # settle through the tool directly — the mint is what M5.4 proves.)
        entitlement_id = consumer_tools.settle(offer)

        assert ada.owner_of(entitlement_id) == ada.address
        assert ada.tok_balance(bell.address) == 10 * 10**18  # Bell paid, via tools
        view = ada.get(entitlement_id)
        assert view.issuer == bell.address and view.params.capacity_bps == 50_000_000
    finally:
        bell.close()
        ada.close()


def test_chain_tools_expose_the_five_operations(anvil):
    from chainmcp.mcp_server import chain_tools

    ada = ChainClient(anvil.rpc_url, ANVIL_KEYS["ada"], deployment=anvil.deployment)
    try:
        tools = chain_tools(ada)
        assert set(tools) == {
            "sign_offer",
            "fulfill_offer",
            "read_entitlement",
            "sign_activation_proof",
            "faucet",
        }
        # the tools return plain JSON-able dicts, not python objects or keys
        result = tools["faucet"](10**18)
        assert isinstance(result["tx_hash"], str) and result["tx_hash"].startswith("0x")
    finally:
        ada.close()
