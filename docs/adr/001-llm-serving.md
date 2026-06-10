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
