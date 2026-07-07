"""The provider agent's graph (M5.3): receive need → admission control → quote or decline.

Two gates, and they are different in kind:

1. **Admission control** — DETERMINISTIC (a capacity ledger per window). "Can I
   physically commit this bandwidth without overselling?" is not a judgment call; it is
   arithmetic, and the answer must be reproducible (story ch. 8: no overselling). Over
   capacity → an immediate §1.2 decline, no LLM involved.

2. **The quote** — the provider's LLM judgment slot (rule 1): given that capacity
   exists, price the offer (or decline for business reasons). This is the mirror of the
   consumer's accept/reject.

So a provider can decline for two reasons — "I physically can't" (ledger) or "I won't at
that price" (LLM) — and only the second is judgment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from a2a_interfaces import BandwidthNeed, Decline, ServiceNeed, SignedOffer

from .llm import LLMClient, StructuredError


class CapacityLedger:
    """Per-window reserved bandwidth. The overselling guard, as arithmetic.

    Keyed by (start, end): reservations only conflict within the same window (v0's
    windows are absolute and identical for the canonical example; overlapping-window
    accounting is a later refinement, not needed for no-overselling of the same slot).
    """

    def __init__(self, capacity_bps: int) -> None:
        self._capacity = capacity_bps
        self._reserved: dict[tuple[int, int], int] = {}

    def available(self, window: tuple[int, int]) -> int:
        return self._capacity - self._reserved.get(window, 0)

    def try_reserve(self, window: tuple[int, int], bps: int) -> bool:
        """Reserve `bps` in `window` if it fits; else leave the ledger untouched and
        return False. All-or-nothing, so a rejected reservation oversells nothing."""
        if bps > self.available(window):
            return False
        self._reserved[window] = self._reserved.get(window, 0) + bps
        return True

    def release(self, window: tuple[int, int], bps: int) -> None:
        self._reserved[window] = max(0, self._reserved.get(window, 0) - bps)


class QuoteDecision(BaseModel):
    """The provider's LLM output: quote at a price, or decline with a reason. Kept in
    `agents` (not interfaces) — it is the provider's internal reasoning, never on the
    wire; what crosses the wire is a SignedOffer or a Decline."""

    quote: bool
    price_tok: int
    reason: str


class ProviderTools(Protocol):
    """What the provider graph needs to sign (a chainmcp stub now, MCP at M5.4)."""

    def sign_offer(self, need: BandwidthNeed, price_tok: int) -> SignedOffer: ...


@dataclass
class ProviderState:
    need: ServiceNeed
    admitted: bool = False
    result: SignedOffer | Decline | None = None
    transcript: list[str] = field(default_factory=list)


_QUOTE_SYSTEM = (
    "You are a network provider pricing a bandwidth request you CAN fulfill (capacity is "
    "confirmed available). Quote a fair price in whole TOK, or decline for a business "
    "reason. Typical rate: about 1 TOK per 5 Mbps."
)


def build_provider_graph(llm: LLMClient, tools: ProviderTools, ledger: CapacityLedger):
    def admit(state: ProviderState) -> ProviderState:
        need = state.need
        window = (need.window.start, need.window.end)
        bps = getattr(need, "capacity_bps", 0)
        state.admitted = ledger.try_reserve(window, bps)
        if state.admitted:
            state.transcript.append(f"admit: reserved {bps // 1_000_000} Mbps in window")
        else:
            state.result = Decline(reason="insufficient capacity in the requested window")
            state.transcript.append("admit: over capacity → decline (no overselling)")
        return state

    def quote(state: ProviderState) -> ProviderState:
        need = state.need
        window = (need.window.start, need.window.end)
        user = f"Price this request: {need.model_dump_json()}"
        try:
            decision = llm.structured(_QUOTE_SYSTEM, user, QuoteDecision)
        except StructuredError:
            decision = QuoteDecision(quote=False, price_tok=0, reason="could not price; declining")
        if decision.quote:
            state.result = tools.sign_offer(need, decision.price_tok)
            state.transcript.append(f"quote: signed offer at {decision.price_tok} TOK")
        else:
            ledger.release(window, getattr(need, "capacity_bps", 0))  # give the slot back
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
