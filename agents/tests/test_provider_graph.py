"""M5.3 — the provider graph. Admission control is deterministic (tested without a
model); the quote slot is stubbed OR runs the deterministic list-price policy
(`llm=None`). The headline is ch. 8's no-overselling as a test — now for BOTH
services, because admission reserves real units for each (catalogue demand)."""

from __future__ import annotations

from a2a_interfaces import Decline, SignedOffer
from a2a_interfaces.fixtures import CANONICAL_SIGNED_OFFER, TELEMETRY_NEED, WINDOW

from agents.provider_graph import (
    QUOTE_SYSTEM,
    CapacityLedger,
    ProviderState,
    QuoteDecision,
    build_provider_graph,
)
from tests_support import bandwidth_need_for  # see conftest-added path below


class _FakeLLM:
    def __init__(self, decision: QuoteDecision) -> None:
        self._decision = decision

    def structured(self, system, user, schema):
        return self._decision


class _SignTool:
    def sign_offer(self, need, price_tok):
        return CANONICAL_SIGNED_OFFER


WINDOW_T = (WINDOW.start, WINDOW.end)


def _quoting_graph(ledger, quote=True, price=10):
    llm = _FakeLLM(QuoteDecision(quote=quote, price_tok=price, reason="scripted"))
    return build_provider_graph(llm, _SignTool(), ledger)


def test_admits_and_quotes_when_capacity_available():
    ledger = CapacityLedger(capacity=100_000_000)
    graph = _quoting_graph(ledger)
    result = graph.invoke(ProviderState(need=bandwidth_need_for(60_000_000)))
    assert isinstance(result["result"], SignedOffer)
    assert ledger.available(WINDOW_T) == 40_000_000  # 60 reserved of 100


def test_no_overselling_second_60_of_100_declines():
    """Story ch. 8, as a test: 60 Mbps twice against a 100 Mbps ledger — the second
    request is physically refused, BEFORE any LLM is asked."""
    ledger = CapacityLedger(capacity=100_000_000)
    graph = _quoting_graph(ledger)

    first = graph.invoke(ProviderState(need=bandwidth_need_for(60_000_000)))
    assert isinstance(first["result"], SignedOffer)

    second = graph.invoke(ProviderState(need=bandwidth_need_for(60_000_000)))
    assert isinstance(second["result"], Decline)
    assert "capacity" in second["result"].reason
    assert "no overselling" in " ".join(second["transcript"])


def test_llm_decline_releases_the_reservation():
    # If the LLM declines to quote, the tentatively-reserved capacity must be freed —
    # a business decline must not silently consume the slot.
    ledger = CapacityLedger(capacity=100_000_000)
    graph = _quoting_graph(ledger, quote=False)
    result = graph.invoke(ProviderState(need=bandwidth_need_for(60_000_000)))
    assert isinstance(result["result"], Decline)
    assert ledger.available(WINDOW_T) == 100_000_000  # slot returned


def test_capacity_ledger_is_all_or_nothing():
    ledger = CapacityLedger(capacity=100)
    assert ledger.try_reserve((0, 10), 60) is True
    assert ledger.try_reserve((0, 10), 60) is False  # would oversell
    assert ledger.available((0, 10)) == 40  # unchanged by the failed reserve


def test_deterministic_slot_quotes_the_list_price():
    """llm=None runs the SAME graph with the judgment slot swapped for the catalogue
    list price — the evaluation's det condition, as one code path."""
    ledger = CapacityLedger(capacity=100_000_000)
    graph = build_provider_graph(None, _SignTool(), ledger)
    result = graph.invoke(ProviderState(need=bandwidth_need_for(50_000_000)))
    assert isinstance(result["result"], SignedOffer)
    assert any("10 TOK" in line for line in result["transcript"])  # bandwidth list price


def test_telemetry_admission_reserves_a_real_slot():
    """Telemetry demand is 1 collector slot (catalogue), not the old `getattr(...,
    'capacity_bps', 0)` vacuous reserve — a 1-slot ledger declines the second sale."""
    ledger = CapacityLedger(capacity=1)
    graph = build_provider_graph(None, _SignTool(), ledger)
    first = graph.invoke(ProviderState(need=TELEMETRY_NEED))
    assert isinstance(first["result"], SignedOffer)
    second = graph.invoke(ProviderState(need=TELEMETRY_NEED))
    assert isinstance(second["result"], Decline)
    assert "capacity" in second["result"].reason


def test_quote_prompt_is_service_neutral():
    # R6 reaches the prompt: what is sold arrives as data (the need + list price)
    assert "bandwidth" not in QUOTE_SYSTEM.lower()
    assert "telemetry" not in QUOTE_SYSTEM.lower()
