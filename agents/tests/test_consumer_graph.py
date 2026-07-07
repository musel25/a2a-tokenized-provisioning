"""M5.2 — the consumer graph, driven by a STUBBED decision so it runs in CI (no model).

The graph's structure is deterministic; only the `decide` slot is an LLM. We inject a
fake LLM whose `structured` returns a scripted DecisionOutput, so we test both the happy
path and the graceful decline branch without a model server."""

from __future__ import annotations

from a2a_interfaces import DecisionOutput
from a2a_interfaces.fixtures import BANDWIDTH_NEED, CANONICAL_SIGNED_OFFER

from agents.consumer_graph import ConsumerState, build_consumer_graph


class _FakeLLM:
    """An LLMClient stand-in: its structured() returns a fixed decision."""

    def __init__(self, accept: bool) -> None:
        self._decision = DecisionOutput(accept=accept, reason="scripted for the test")

    def structured(self, system, user, schema):
        return self._decision


class _StubTools:
    def __init__(self) -> None:
        self.settled = False
        self.activated = False

    def quote(self, need):
        return CANONICAL_SIGNED_OFFER

    def settle(self, offer):
        self.settled = True
        return 7

    def activate(self, entitlement_id):
        self.activated = True
        return f"ent{entitlement_id}-a0"


def _run(accept: bool):
    tools = _StubTools()
    graph = build_consumer_graph(_FakeLLM(accept), tools)
    result = graph.invoke(ConsumerState(need=BANDWIDTH_NEED, budget_tok=15))
    return tools, result


def test_happy_path_buys_and_activates():
    tools, result = _run(accept=True)
    assert tools.settled and tools.activated
    assert result["entitlement_id"] == 7
    assert result["session_id"] == "ent7-a0"
    # the transcript reads like the lifecycle (docs/01 M5.2 "transcript shows happy path")
    steps = [line.split(":")[0] for line in result["transcript"]]
    assert steps == ["quote", "decide", "settle", "activate", "report"]


def test_decline_exits_gracefully_without_buying():
    tools, result = _run(accept=False)
    assert not tools.settled and not tools.activated
    assert result["entitlement_id"] is None and result["session_id"] is None
    steps = [line.split(":")[0] for line in result["transcript"]]
    assert steps == ["quote", "decide", "exit"]
