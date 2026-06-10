# agents — the brains

LangGraph graphs (consumer, bandwidth provider, telemetry provider), the
OpenAI-compatible LLM client (ADR-001), MCP clients, and A2A adapters (ADR-002,
SDK imports confined to `*/a2a_adapter.py`). LLM judgment lives at exactly two points:
the consumer's accept/reject and the provider's quote/decline.

- Arrives: M5.1–M5.6 (Phase 5)
- May depend on: `interfaces`
