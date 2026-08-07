"""The consumer agent's graph (M5.2): discover → quote → decide → settle → activate → report.

A LangGraph state machine, but the *tools* are plain injected callables here (graphs
before MCP — two new technologies never land in the same milestone, docs/01 M5.2). The
one judgment slot is `decide`; everything else is mechanical. `llm=None` swaps the slot
for the deterministic policy (accept iff the price fits the budget), so the SAME graph
runs in both evaluation conditions. A provider `Decline` or a reject decision exits the
graph gracefully, never reaching settlement.

The tools are a Protocol so M5.4 can swap the stubs for MCP-backed implementations
without touching the graph — the same move the controller made with its ports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from langgraph.graph import END, StateGraph

from a2a_interfaces import Decline, DecisionOutput, ServiceNeed, SignedOffer

from .decision import decide
from .llm import LLMClient


class ConsumerTools(Protocol):
    """What the consumer graph needs from the outside world (stubs now, MCP at M5.4)."""

    def quote(self, need: ServiceNeed) -> SignedOffer | Decline: ...
    def settle(self, offer: SignedOffer) -> int: ...  # returns entitlement_id
    def activate(self, entitlement_id: int, kind: str) -> str: ...  # returns session_id


@dataclass
class ConsumerState:
    """Threaded through the graph; each node fills the next field."""

    need: ServiceNeed
    budget_tok: int
    offer: SignedOffer | None = None
    decision: DecisionOutput | None = None
    entitlement_id: int | None = None
    session_id: str | None = None
    transcript: list[str] = field(default_factory=list)


def build_consumer_graph(llm: LLMClient | None, tools: ConsumerTools):
    """Compile the graph. `decide` branches to settlement or a graceful decline."""

    def request_quote(state: ConsumerState) -> ConsumerState:
        result = tools.quote(state.need)
        if isinstance(result, Decline):
            state.transcript.append(f"quote: provider declined — {result.reason}")
            return state
        state.offer = result
        price = int(state.offer.offer.price) // 10**18
        state.transcript.append(f"quote: {price} TOK for {state.need.kind}")
        return state

    def make_decision(state: ConsumerState) -> ConsumerState:
        if llm is None:  # the deterministic slot: one comparison, no judgment exercised
            price = int(state.offer.offer.price) // 10**18
            ok = price <= state.budget_tok
            state.decision = DecisionOutput(
                accept=ok,
                reason=f"deterministic policy: {price} TOK "
                f"{'within' if ok else 'over'} budget {state.budget_tok} TOK",
            )
        else:
            state.decision = decide(llm, state.need, state.offer, state.budget_tok)
        verb = "accept" if state.decision.accept else "decline"
        state.transcript.append(f"decide: {verb} — {state.decision.reason}")
        return state

    def settle(state: ConsumerState) -> ConsumerState:
        state.entitlement_id = tools.settle(state.offer)
        state.transcript.append(f"settle: minted entitlement #{state.entitlement_id}")
        return state

    def activate(state: ConsumerState) -> ConsumerState:
        state.session_id = tools.activate(state.entitlement_id, state.need.kind)
        state.transcript.append(f"activate: session {state.session_id} active")
        return state

    def report(state: ConsumerState) -> ConsumerState:
        state.transcript.append("report: service running")
        return state

    def declined(state: ConsumerState) -> ConsumerState:
        state.transcript.append("exit: offer declined, nothing purchased")
        return state

    graph = StateGraph(ConsumerState)
    graph.add_node("request_quote", request_quote)
    graph.add_node("decide", make_decision)
    graph.add_node("settle", settle)
    graph.add_node("activate", activate)
    graph.add_node("report", report)
    graph.add_node("declined", declined)

    graph.set_entry_point("request_quote")
    graph.add_conditional_edges(
        "request_quote",
        lambda s: "decide" if s.offer is not None else "declined",
        {"decide": "decide", "declined": "declined"},
    )
    graph.add_conditional_edges(
        "decide",
        lambda s: "settle" if s.decision.accept else "declined",
        {"settle": "settle", "declined": "declined"},
    )
    graph.add_edge("settle", "activate")
    graph.add_edge("activate", "report")
    graph.add_edge("report", END)
    graph.add_edge("declined", END)
    return graph.compile()
