"""M5.1 acceptance: 20/20 schema-valid decisions against a live Ollama, and the
validator makes backend differences irrelevant (the same asserts hold for any model)."""

from __future__ import annotations

import pytest

from a2a_interfaces import DecisionOutput
from a2a_interfaces.fixtures import BANDWIDTH_NEED, CANONICAL_SIGNED_OFFER

from agents.decision import decide
from agents.llm import LLMClient

from agents.llm import ollama_up

pytestmark = pytest.mark.skipif(not ollama_up(), reason="needs a local Ollama at LLM_BASE_URL")


def test_20_of_20_valid_decisions(llm_config):
    """Every one of 20 runs yields a schema-valid DecisionOutput — that's the ADR-001
    contract, not the specific verdict (the LLM may reasonably accept or reject)."""
    client = LLMClient(llm_config)
    for _ in range(20):
        out = decide(client, BANDWIDTH_NEED, CANONICAL_SIGNED_OFFER, budget_tok=15)
        assert isinstance(out, DecisionOutput)
        assert isinstance(out.accept, bool) and out.reason


def test_accepts_a_good_deal(llm_config):
    # 10 TOK for the exact need, well under a 20 TOK budget — a decisive model accepts.
    client = LLMClient(llm_config)
    out = decide(client, BANDWIDTH_NEED, CANONICAL_SIGNED_OFFER, budget_tok=20)
    assert out.accept, out.reason


def test_rejects_when_over_budget(llm_config):
    # Same 10 TOK offer, but the budget is 5 — it must not accept.
    client = LLMClient(llm_config)
    out = decide(client, BANDWIDTH_NEED, CANONICAL_SIGNED_OFFER, budget_tok=5)
    assert not out.accept, out.reason
