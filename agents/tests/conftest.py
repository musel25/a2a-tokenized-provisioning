"""LLM fixtures: a live Ollama when present (the real ADR-001 target), else skip.

CI has no model server, so the live tests skip there; the stub-backed tests
(test_llm_retry) run everywhere and pin the validate-and-retry logic without a model.
"""

from __future__ import annotations

import os

import pytest

from agents.llm import LLMConfig, ollama_up

OLLAMA = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1")
requires_llm = pytest.mark.skipif(not ollama_up(), reason="needs a local Ollama at LLM_BASE_URL")


@pytest.fixture()
def llm_config() -> LLMConfig:
    # qwen3:4b is the recorded defense-day model (fits the lab PC, decisive enough).
    return LLMConfig(
        base_url=OLLAMA,
        model=os.environ.get("LLM_MODEL", "qwen3:4b"),
        api_key="ollama",
    )
