"""The provider agent's graph (M5.3): receive need → admission control → quote or decline.

Two gates, and they are different in kind:

1. **Admission control** — DETERMINISTIC (a capacity ledger per window). "Can I
   physically commit this resource without overselling?" is not a judgment call; it is
   arithmetic, and the answer must be reproducible (story ch. 8: no overselling). Over
   capacity → an immediate §1.2 decline, no LLM involved.

2. **The quote** — the provider's judgment slot (rule 1): given that capacity exists,
   price the offer (or decline for business reasons). `llm=None` swaps the slot for a
   deterministic policy — quote the catalogue list price — so the SAME graph runs in
   both evaluation conditions and the det/llm delta is the model call, nothing else.

What is sold appears nowhere in this file's logic: demand, list price, and display
units come from the catalogue (`agents.catalogue`), the agent-layer twin of
controller/translators.py. A provider can decline for two reasons — "I physically
can't" (ledger) or "I won't at that price" (judgment) — and only the second is judgment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from a2a_interfaces import Decline, ServiceNeed, SignedOffer

from .catalogue import service_for
from .llm import LLMClient, StructuredError


class CapacityLedger:
    """Per-window reserved units. The overselling guard, as arithmetic.

    The units are the catalogue's business (bps for bandwidth, collector slots for
    telemetry) — the ledger only adds and compares. Keyed by (start, end):
    reservations only conflict within the same window (v0's windows are absolute and
    identical for the canonical example; overlapping-window accounting is a later
    refinement, not needed for no-overselling of the same slot).
    """

    def __init__(self, capacity: int) -> None:
        self._capacity = capacity
        self._reserved: dict[tuple[int, int], int] = {}

    def available(self, window: tuple[int, int]) -> int:
        return self._capacity - self._reserved.get(window, 0)

    def try_reserve(self, window: tuple[int, int], units: int) -> bool:
        """Reserve `units` in `window` if they fit; else leave the ledger untouched and
        return False. All-or-nothing, so a rejected reservation oversells nothing."""
        if units > self.available(window):
            return False
        self._reserved[window] = self._reserved.get(window, 0) + units
        return True

    def release(self, window: tuple[int, int], units: int) -> None:
        self._reserved[window] = max(0, self._reserved.get(window, 0) - units)


class QuoteDecision(BaseModel):
    """The provider's judgment output: quote at a price, or decline with a reason. Kept
    in `agents` (not interfaces) — it is the provider's internal reasoning, never on the
    wire; what crosses the wire is a SignedOffer or a Decline."""

    quote: bool
    price_tok: int
    reason: str


class ProviderTools(Protocol):
    """What the provider graph needs to sign (a chainmcp stub now, MCP at M5.4)."""

    def sign_offer(self, need: ServiceNeed, price_tok: int) -> SignedOffer: ...


@dataclass
class ProviderState:
    need: ServiceNeed
    admitted: bool = False
    result: SignedOffer | Decline | None = None
    transcript: list[str] = field(default_factory=list)


QUOTE_SYSTEM = (
    "You are a network-service provider pricing one quote. Capacity is confirmed "
    "available. Quote a fair whole-TOK price between 5 and 25, or decline for a "
    "business reason."
)


def quote_user_message(need: ServiceNeed, list_price_tok: int) -> str:
    """The judgment slot's input: the per-service facts travel as data, so the system
    prompt stays service-neutral (R6 reaches the prompt, not just the code)."""
    return f"LIST PRICE: {list_price_tok} TOK\nNEED: {need.model_dump_json()}"


def build_provider_graph(llm: LLMClient | None, tools: ProviderTools, ledger: CapacityLedger):
    def admit(state: ProviderState) -> ProviderState:
        need = state.need
        svc = service_for(need.kind)
        window = (need.window.start, need.window.end)
        units = svc.demand(need)
        state.admitted = ledger.try_reserve(window, units)
        if state.admitted:
            state.transcript.append(f"admit: reserved {svc.fmt(units)} in window")
        else:
            state.result = Decline(reason="insufficient capacity in the requested window")
            state.transcript.append("admit: over capacity → decline (no overselling)")
        return state

    def quote(state: ProviderState) -> ProviderState:
        need = state.need
        svc = service_for(need.kind)
        window = (need.window.start, need.window.end)
        if llm is None:  # the deterministic slot: list price, no judgment exercised
            decision = QuoteDecision(
                quote=True, price_tok=svc.list_price_tok, reason="list price (deterministic slot)"
            )
        else:
            try:
                decision = llm.structured(
                    QUOTE_SYSTEM, quote_user_message(need, svc.list_price_tok), QuoteDecision
                )
            except StructuredError:
                decision = QuoteDecision(quote=False, price_tok=0, reason="could not price; declining")
        if decision.quote:
            state.result = tools.sign_offer(need, decision.price_tok)
            state.transcript.append(f"quote: signed offer at {decision.price_tok} TOK")
        else:
            ledger.release(window, svc.demand(need))  # give the slot back
            state.result = Decline(reason=decision.reason)
            state.transcript.append(f"quote: declined — {decision.reason}")
        return state

    graph = StateGraph(ProviderState)
    graph.add_node("admit", admit)
    graph.add_node("quote", quote)
    graph.set_entry_point("admit")
    graph.add_conditional_edges(
        "admit", lambda s: "quote" if s.admitted else END, {"quote": "quote", END: END}
    )
    graph.add_edge("quote", END)
    return graph.compile()
