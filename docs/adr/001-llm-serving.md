# ADR-001 — LLM serving: OpenAI-compatible endpoint, backend-agnostic

**Status:** accepted · 2026-06-09

## Context
Agents need an LLM. Requirements: run locally on the dev PC (Ollama), run on Modal-hosted
vLLM for heavier models, and never be locked to either. Ollama and vLLM both expose an
OpenAI-compatible `/v1/chat/completions` endpoint; Modal's standard vLLM deployment serves
the same behind HTTPS (with proxy-auth token).

## Decision
Agent code talks **only** to an OpenAI-compatible chat endpoint. The backend is selected by
environment, never by code:

```
LLM_BASE_URL   http://localhost:11434/v1   |  https://<app>.modal.run/v1  |  any other
LLM_MODEL      qwen3:4b                    |  Qwen/Qwen3-4B               |  ...
LLM_API_KEY    dummy                       |  <modal proxy token>         |  ...
```

Structured outputs are requested via JSON schema, then **always validated and retried in
code** (backends differ in structured-output flavor; the guard makes that irrelevant).

## Consequences
- Swap backends with three env vars; CI can run a stub server.
- Defense-day rule: run local Ollama — no network dependency in the room. Modal is for dev.
- Limited to the common API subset — acceptable: we need chat + structured output only.
- Cold starts on Modal are tolerable in dev, not in the live demo.

## Amendment — 2026-07-07: the Modal leg is built, and it IS the live-demo backend

The dev box turned out too RAM-starved for interactive local judgment (~140 s/decision
on qwen3:4b), so the operator console shipped with deterministic stand-ins in the two
judgment slots. That inverted the last two consequences: the live demo now runs
**Modal-hosted vLLM** (`llmserve/modal_llm.py` — Qwen3-4B on an L4, OpenAI-compatible,
scale-to-zero), selected by the same three env vars via a repo-root `.env`
(`just` loads it; `A2A_LIVE_LLM=1` arms the slots).

Cold starts are handled, not suffered: the console server probes-and-warms the endpoint
at startup (`Console.warm_llm`, generic `agents.llm.llm_up`), the container stays warm
15 min past the last call, and the header pill shows `judgment · qwen3-4b / warming /
deterministic` honestly. **The deterministic stand-ins remain the no-network fallback**
— the defense-day rule is now "the demo must not *require* the network", not "no
network in the room". Local Ollama remains a third interchangeable backend, unchanged.
