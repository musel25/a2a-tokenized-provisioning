"""M5.2 — the consumer graph, driven by a STUBBED decision so it runs in CI (no model).

The graph's structure is deterministic; only the `decide` slot is judgment. We inject a
fake LLM whose `structured` returns a scripted DecisionOutput — or `llm=None`, which
runs the deterministic budget policy through the SAME graph (the evaluation's det
condition). Both the graceful consumer decline and the provider `Decline` exit before
settlement."""

from __future__ import annotations

from a2a_interfaces import Decline, DecisionOutput
from a2a_interfaces.fixtures import BANDWIDTH_NEED, CANONICAL_SIGNED_OFFER, TELEMETRY_NEED

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
        self.activated_kind: str | None = None

    def quote(self, need):
        return CANONICAL_SIGNED_OFFER

    def settle(self, offer):
        self.settled = True
        return 7

    def activate(self, entitlement_id, kind):
        self.activated = True
        self.activated_kind = kind
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
    assert tools.activated_kind == "bandwidth"  # the action names what the need asked
    # the transcript reads like the lifecycle (docs/01 M5.2 "transcript shows happy path")
    steps = [line.split(":")[0] for line in result["transcript"]]
    assert steps == ["quote", "decide", "settle", "activate", "report"]


def test_decline_exits_gracefully_without_buying():
    tools, result = _run(accept=False)
    assert not tools.settled and not tools.activated
    assert result["entitlement_id"] is None and result["session_id"] is None
    steps = [line.split(":")[0] for line in result["transcript"]]
    assert steps == ["quote", "decide", "exit"]


def test_deterministic_slot_buys_within_budget_without_a_model():
    """llm=None: the same graph, the decide slot swapped for one comparison."""
    tools = _StubTools()
    graph = build_consumer_graph(None, tools)
    result = graph.invoke(ConsumerState(need=BANDWIDTH_NEED, budget_tok=15))
    assert tools.settled and result["session_id"] == "ent7-a0"  # 10 TOK ≤ 15 TOK


def test_deterministic_slot_declines_over_budget():
    tools = _StubTools()
    graph = build_consumer_graph(None, tools)  # canonical offer prices at 10 TOK
    result = graph.invoke(ConsumerState(need=BANDWIDTH_NEED, budget_tok=9))
    assert not tools.settled and result["entitlement_id"] is None


def test_telemetry_need_activates_with_its_own_kind():
    tools = _StubTools()
    graph = build_consumer_graph(None, tools)
    graph.invoke(ConsumerState(need=TELEMETRY_NEED, budget_tok=15))
    assert tools.activated_kind == "telemetry"


def test_provider_decline_routes_to_graceful_exit():
    """A Decline from the provider (e.g. admission refused the reservation) must exit
    before the decide slot — there is nothing to judge."""

    class _DecliningTools(_StubTools):
        def quote(self, need):
            return Decline(reason="insufficient capacity in the requested window")

    tools = _DecliningTools()
    graph = build_consumer_graph(None, tools)
    result = graph.invoke(ConsumerState(need=BANDWIDTH_NEED, budget_tok=15))
    assert not tools.settled
    steps = [line.split(":")[0] for line in result["transcript"]]
    assert steps == ["quote", "exit"]
