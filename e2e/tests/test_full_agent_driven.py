"""M5.6 — skeleton v4: the REAL agent graphs drive the whole flow (the 'full' profile).

The scripted agents are gone; the consumer graph and provider graph run the lifecycle
against real chainmcp tools, a real controller, and real Anvil state. This IS the system
test now.

Nondeterminism is the point (docs/01 M5.6 "watch for"): with a real LLM the consumer may
accept or decline, so the assertions check VALID BEHAVIOR (schema + invariants), not one
fixed path. Two ways to run it:

- always (CI-safe, deterministic): a controllable fake LLM stands in the two judgment
  slots, so the WIRING of real-graphs → real-chain → real-controller is proven without a
  model.
- opt-in live: set A2A_LIVE_LLM=1 with a fast Ollama to drive the same graphs with real
  judgment (skipped here — the shared box serves qwen3:4b at ~140 s/decision).
"""

from __future__ import annotations

import os

import pytest

from a2a_interfaces import DecisionOutput, SessionState, SignedOffer
from a2a_interfaces.fixtures import BANDWIDTH_NEED
from chainmcp import ChainClient
from chainmcp.testing import ANVIL_KEYS, anvil_available, artifacts_available, launch_anvil

from agents.consumer_graph import ConsumerState, build_consumer_graph
from agents.mcp_tools import ChainConsumerTools, ChainProviderTools
from agents.provider_graph import CapacityLedger, ProviderState, QuoteDecision, build_provider_graph

pytestmark = pytest.mark.skipif(
    not (anvil_available() and artifacts_available()),
    reason="skeleton v4 needs Anvil + forge artifacts",
)

STORY_TIME = 1757944800 - 1680  # 13:32


class _FakeLLM:
    """Stands in the two judgment slots. `decision` is what it always returns."""

    def __init__(self, decision):
        self._d = decision

    def structured(self, *a):
        return self._d


def _seed_six_presales(anvil):
    """Make Ada's ticket literally #7 (six earlier sales, Bell→Carol)."""
    from a2a_interfaces.fixtures import CANONICAL_OFFER

    bell = ChainClient(anvil.rpc_url, ANVIL_KEYS["bell"], deployment=anvil.deployment)
    carol = ChainClient(anvil.rpc_url, ANVIL_KEYS["carol"], deployment=anvil.deployment)
    try:
        carol.faucet(60 * 10**18)
        for i in range(1, 7):
            pre = CANONICAL_OFFER.model_copy(update={"salt": "0x" + f"{i:064x}"})
            carol.approve_and_fulfill(bell.sign_offer(pre))
    finally:
        bell.close()
        carol.close()


@pytest.fixture()
def stack():
    from controller.app import build_app
    from controller.auth import AuthStore
    from controller.resource_map import load_resource_map
    from controller.service import ControllerService

    anvil = launch_anvil(timestamp=STORY_TIME)
    _seed_six_presales(anvil)
    bell = ChainClient(anvil.rpc_url, ANVIL_KEYS["bell"], deployment=anvil.deployment)
    ada = ChainClient(anvil.rpc_url, ANVIL_KEYS["ada"], deployment=anvil.deployment)
    ada.faucet(100 * 10**18)

    # A real controller over a read-only chain + a recording provisioner (the network
    # leg is netctl's; the agent-driven proof is about chain+controller+graphs).
    from chainmcp import ChainReader
    from netctl.mock import MockProvisioner

    from fastapi.testclient import TestClient

    reader = ChainReader(anvil.rpc_url, deployment=anvil.deployment)
    net = MockProvisioner()
    service = ControllerService(reader, net, AuthStore("bw-ctrl-1"), load_resource_map())
    # TestClient is a sync httpx.Client bridged to the ASGI app — the same interface a
    # real deployment's client has, so ChainConsumerTools doesn't know it's in-process.
    controller_http = TestClient(build_app(service))
    # move chain time into Ada's window so activation is authorized
    anvil.increase_time(ada._w3, 1800)

    yield anvil, ada, bell, service, net, controller_http
    for c in (bell, ada, reader):
        c.close()
    controller_http.close()
    anvil.stop()


def _run_lifecycle(anvil, ada, bell, controller_http, decision: DecisionOutput):
    """The consumer graph, driven end to end by real tools + a controllable decision."""
    # provider graph signs a real offer via Bell's chainmcp
    provider = build_provider_graph(
        _FakeLLM(QuoteDecision(quote=True, price_tok=10, reason="fair")),
        ChainProviderTools(bell),
        CapacityLedger(capacity_bps=100_000_000),
    )
    offer = provider.invoke(ProviderState(need=BANDWIDTH_NEED))["result"]
    assert isinstance(offer, SignedOffer)

    tools = ChainConsumerTools(
        ada, controller_url=str(controller_http.base_url), http=controller_http
    )
    tools.quote = lambda _need: offer  # A2A brings the quote (M5.5); inject it here
    graph = build_consumer_graph(_FakeLLM(decision), tools)
    return graph.invoke(ConsumerState(need=BANDWIDTH_NEED, budget_tok=15))


def test_agent_driven_happy_path(stack):
    anvil, ada, bell, service, net, controller_http = stack
    result = _run_lifecycle(
        anvil, ada, bell, controller_http, DecisionOutput(accept=True, reason="fits budget")
    )
    # valid behavior for an ACCEPT: bought #7, activated, controller says ACTIVE
    assert result["entitlement_id"] == 7
    assert ada.owner_of(7) == ada.address
    session_id = result["session_id"]
    assert service.session(session_id).state == SessionState.ACTIVE
    assert net.applied[session_id]["capacity_bps"] == 50_000_000


def test_agent_driven_decline_is_also_valid(stack):
    anvil, ada, bell, service, net, controller_http = stack
    result = _run_lifecycle(
        anvil, ada, bell, controller_http, DecisionOutput(accept=False, reason="too pricey")
    )
    # valid behavior for a DECLINE: nothing minted, nothing activated
    assert result["entitlement_id"] is None and result["session_id"] is None
    with pytest.raises(KeyError):
        ada.owner_of(7)


@pytest.mark.skipif(os.environ.get("A2A_LIVE_LLM") != "1", reason="opt-in: needs a fast Ollama")
def test_agent_driven_live_llm_valid_behavior(stack):
    """The same graphs with REAL judgment. Asserts VALID behavior, not a fixed path —
    the LLM may accept or decline, and both are correct outcomes."""
    from agents.decision import decide
    from agents.llm import LLMClient

    anvil, ada, bell, service, net, controller_http = stack
    llm = LLMClient()
    decision = decide(llm, BANDWIDTH_NEED, CANONICAL_SIGNED_OFFER_placeholder(bell), budget_tok=15)
    result = _run_lifecycle(anvil, ada, bell, controller_http, decision)
    if decision.accept:
        assert result["entitlement_id"] == 7
        assert service.session(result["session_id"]).state == SessionState.ACTIVE
    else:
        assert result["entitlement_id"] is None


def CANONICAL_SIGNED_OFFER_placeholder(bell):
    from a2a_interfaces.fixtures import CANONICAL_OFFER

    return bell.sign_offer(CANONICAL_OFFER)
