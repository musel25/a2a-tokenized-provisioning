"""The validate-and-retry loop, pinned WITHOUT a model — a scripted fake OpenAI client
stands in, so this runs in CI. This is the ADR-001 guarantee under test: whatever the
backend emits, the caller gets a valid object or a clean StructuredError."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from agents.llm import LLMClient, LLMConfig, StructuredError, _extract_json


class Decision(BaseModel):
    accept: bool
    reason: str


class _ScriptedChat:
    """Replays a fixed list of assistant replies, one per call."""

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.calls = 0

    def create(self, **_kwargs):
        reply = self._replies[self.calls]
        self.calls += 1
        return type(
            "R", (), {"choices": [type("C", (), {"message": type("M", (), {"content": reply})})]}
        )


def _client_with(replies: list[str]) -> tuple[LLMClient, _ScriptedChat]:
    client = LLMClient(LLMConfig(base_url="x", model="m", api_key="k", max_retries=3))
    chat = _ScriptedChat(replies)
    client._client = type("O", (), {"chat": type("Ch", (), {"completions": chat})})()
    return client, chat


def test_valid_first_try():
    client, chat = _client_with(['{"accept": true, "reason": "meets need"}'])
    out = client.structured("sys", "usr", Decision)
    assert out.accept and chat.calls == 1


def test_retries_then_succeeds():
    client, chat = _client_with(
        ["not json at all", '{"accept": false}', '{"accept": false, "reason": "too pricey"}']
    )
    out = client.structured("sys", "usr", Decision)
    assert out.accept is False and out.reason == "too pricey" and chat.calls == 3


def test_exhausts_retries_and_raises():
    client, chat = _client_with(["nope", "still nope", "nope again"])
    with pytest.raises(StructuredError) as exc:
        client.structured("sys", "usr", Decision)
    assert len(exc.value.attempts) == 3 and chat.calls == 3


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"a": 1}', '{"a": 1}'),
        ('```json\n{"a": 1}\n```', '{"a": 1}'),
        ('here you go: {"a": 1} hope that helps', '{"a": 1}'),
        ('<think>let me see...</think>\n{"a": 1}', '{"a": 1}'),
        ('{"a": {"b": 2}}', '{"a": {"b": 2}}'),  # balanced, not first close-brace
    ],
)
def test_extract_json_tolerates_wrappers(raw, expected):
    assert _extract_json(raw) == expected
