"""The LLM client (ADR-001): an OpenAI-compatible endpoint, chosen by env, whose
structured output is ALWAYS validated against a pydantic model and retried in code.

The validate-and-retry loop is the load-bearing idea: backends disagree on how (or
whether) they honor a JSON schema, and small local models wander. By parsing every
response into the target pydantic model and re-prompting on failure, the rest of the
system sees a guaranteed-valid object or a clean exception — never a raw string, never
a backend quirk. This is why the same test passes against Ollama, vLLM, or a stub.

This module is the ONLY place `agents` imports an LLM SDK. It uses the generic `openai`
client (rule: no backend-specific SDK) pointed wherever LLM_BASE_URL says.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class StructuredError(RuntimeError):
    """The model could not produce a schema-valid object within the retry budget.

    Carries the attempts so a caller (or a test) can see what the model actually said.
    In the graphs this maps to a safe default: a decline / reject, never a crash.
    """

    def __init__(self, attempts: list[str]) -> None:
        super().__init__(f"no valid structured output in {len(attempts)} attempts")
        self.attempts = attempts


@dataclass(frozen=True)
class LLMConfig:
    """Three env vars, per ADR-001 — nothing backend-specific in code."""

    base_url: str
    model: str
    api_key: str
    max_retries: int = 3
    temperature: float = 0.0  # decisions want determinism, not creativity

    @classmethod
    def from_env(cls) -> LLMConfig:
        return cls(
            base_url=os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1"),
            model=os.environ.get("LLM_MODEL", "qwen3:4b"),
            api_key=os.environ.get("LLM_API_KEY", "ollama"),  # local Ollama ignores it
        )


class LLMClient:
    """A thin validate-and-retry wrapper over chat/completions."""

    def __init__(self, config: LLMConfig | None = None) -> None:
        self._config = config or LLMConfig.from_env()
        self._client = OpenAI(base_url=self._config.base_url, api_key=self._config.api_key)
        # Observability for evaluation (docs/09): what the LAST structured() call cost.
        # Read-only breadcrumbs — no behavior depends on them.
        self.last_attempts: int = 0
        self.last_usage: dict = {}

    def structured(self, system: str, user: str, schema: type[T]) -> T:
        """Return an instance of `schema`, or raise StructuredError after the retries.

        Each attempt asks for JSON matching the model's schema; the reply is stripped of
        any prose/markdown/thinking fences a small model may wrap it in, then validated.
        """
        # Strip the top-level description (the pydantic class docstring): a long one reads
        # like a document to reproduce, and literal-minded instruct models echo the schema
        # back instead of producing an instance (observed with Qwen3-4B-Instruct-2507).
        schema_json = schema.model_json_schema()
        schema_json.pop("description", None)
        instruction = (
            "Respond with ONLY a single JSON object — an INSTANCE with concrete values "
            "conforming to this schema, never the schema itself. No prose, no markdown "
            "fences:\n" + json.dumps(schema_json)
        )
        attempts: list[str] = []
        self.last_usage = {}
        for _ in range(self._config.max_retries):
            reply = self._chat(system + "\n\n" + instruction, user)
            attempts.append(reply)
            self.last_attempts = len(attempts)
            try:
                return schema.model_validate_json(_extract_json(reply))
            except (ValidationError, ValueError):
                continue
        raise StructuredError(attempts)

    def _chat(self, system: str, user: str) -> str:
        response = self._client.chat.completions.create(
            model=self._config.model,
            temperature=self._config.temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        if response.usage is not None:  # accumulate across retries within one structured()
            self.last_usage = {
                "prompt_tokens": self.last_usage.get("prompt_tokens", 0)
                + (response.usage.prompt_tokens or 0),
                "completion_tokens": self.last_usage.get("completion_tokens", 0)
                + (response.usage.completion_tokens or 0),
            }
        return response.choices[0].message.content or ""


def llm_up(config: LLMConfig | None = None, timeout: float = 20.0) -> bool:
    """Is the configured OpenAI-compatible endpoint SERVING? Backend-agnostic sibling of
    `ollama_up` (same bounded-generation idea — see its docstring): a 1-token completion
    against /chat/completions with a deadline, so it works for vLLM/Modal, Ollama, or any
    /v1 endpoint. A cold serverless container that boots slower than `timeout` reports
    False — callers treat that as 'warming', not 'absent', and probe again."""
    import httpx

    cfg = config or LLMConfig.from_env()
    try:
        response = httpx.post(
            cfg.base_url.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {cfg.api_key}"},
            json={
                "model": cfg.model,
                "messages": [{"role": "user", "content": "ok"}],
                "max_tokens": 1,
            },
            timeout=timeout,
        )
        return response.status_code == 200
    except Exception:
        return False


def ollama_up(base_url: str | None = None, model: str | None = None) -> bool:
    """Is a local Ollama actually SERVING (not just alive)? A bounded generation probe,
    not a mere /api/tags ping: a wedged runner answers /api/tags while every generation
    hangs, so tests keyed on the ping would hang too. This probes a 1-token completion
    with a tight deadline — healthy ≈ a second, wedged/absent → False, tests skip clean."""
    import httpx

    url = base_url or os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1")
    model = model or os.environ.get("LLM_MODEL", "qwen3:4b")
    try:
        response = httpx.post(
            url.replace("/v1", "/api/chat"),
            json={
                "model": model,
                "messages": [{"role": "user", "content": "ok"}],
                "stream": False,
                "options": {"num_predict": 1},
            },
            timeout=20.0,
        )
        return response.status_code == 200
    except Exception:
        return False


def _extract_json(text: str) -> str:
    """Pull the first balanced {...} out of a reply, tolerating ```json fences and the
    <think>…</think> blocks reasoning models (qwen3) emit before their answer."""
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[1]
    start = text.find("{")
    if start == -1:
        return text
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]
