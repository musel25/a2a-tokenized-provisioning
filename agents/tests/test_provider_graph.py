"""M5.3 — the provider graph. Admission control is deterministic (tested without a
model); the quote slot is stubbed OR runs the deterministic list-price policy
(`llm=None`). The headline is ch. 8's no-overselling as a test — now for BOTH
services, because admission reserves real units for each (catalogue demand)."""

from __future__ import annotations

from a2a_interfaces import Decline, SignedOffer
from a2a_interfaces.fixtures import CANONICAL_SIGNED_OFFER, TELEMETRY_NEED, WINDOW

from agents.provider_graph import (
    QUOTE_HOLD_S,
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


def test_concurrent_admissions_cannot_oversell_one_slot():
    """The check-then-act race: `try_reserve` reads `available` and then appends, so
    two threads can both see the same free capacity and both take it.

    The window between the read and the append is a few bytecodes wide, so under the
    GIL it almost never loses the interpreter — a plain thread race passes with or
    without the lock and proves nothing. The clock widens it honestly: `_sweep` calls
    it on every read, so a clock that sleeps yields the GIL *inside* the critical
    section, exactly where a slower real ledger (an RPC, a database) would. Eight
    threads then race for a pool with room for one; exactly one must win."""
    import threading
    import time

    def slow_chain_time() -> int:
        time.sleep(0.005)  # a yield point between the check and the act
        return 1000

    ledger = CapacityLedger(capacity=1, clock=slow_chain_time)
    start = threading.Barrier(8)
    wins: list[bool] = []
    record = threading.Lock()

    def contend() -> None:
        start.wait()  # release every thread into try_reserve together
        got = ledger.try_reserve((0, 10), 1)
        with record:
            wins.append(got)

    threads = [threading.Thread(target=contend) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(wins) == 1, f"{sum(wins)} admissions fit into capacity for one"
    assert ledger.available((0, 10)) == 0


def test_holds_expire_so_quoting_without_accepting_cannot_drain_the_pool():
    """Admission reserves before the price is known, and a consumer may never accept.
    Without an expiry, asking for quotes was enough to exhaust the pool for free."""
    now = [1000]
    ledger = CapacityLedger(capacity=100, clock=lambda: now[0])

    assert ledger.try_reserve((0, 10), 100) is True
    assert ledger.try_reserve((0, 10), 100) is False  # first hold is still live

    now[0] += QUOTE_HOLD_S + 1  # the quote went stale, unaccepted
    assert ledger.available((0, 10)) == 100
    assert ledger.try_reserve((0, 10), 100) is True


def test_a_signed_offer_holds_capacity_until_the_offer_expires():
    """Once signed, the hold tracks the offer the buyer is actually holding — longer
    than the default quote hold, and no longer."""
    now = [1000]
    ledger = CapacityLedger(capacity=100, clock=lambda: now[0])
    ledger.try_reserve((0, 10), 100)
    ledger.hold_until((0, 10), 100, expires_at=now[0] + QUOTE_HOLD_S * 4)

    now[0] += QUOTE_HOLD_S + 1  # past the default hold, still inside offer validity
    assert ledger.available((0, 10)) == 0

    now[0] += QUOTE_HOLD_S * 4
    assert ledger.available((0, 10)) == 100  # offer lapsed, capacity back on the market


def test_a_ledger_without_a_clock_never_expires_a_hold():
    """The unit-test and det-condition behaviour, unchanged: no clock, no expiry."""
    ledger = CapacityLedger(capacity=100)
    assert ledger.try_reserve((0, 10), 100) is True
    assert ledger.available((0, 10)) == 0


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
