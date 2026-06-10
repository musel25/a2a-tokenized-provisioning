# controller — the bouncer + translator

Deterministic anti-corruption layer: authorization predicate, session state machine,
challenge–response auth, per-serviceType translators, HTTP API (docs/03 §3).
**Never an LLM** (hard rule #1); domain code imports no I/O (hard rule #4); owns the
`resourceId → topology` map (`resource_map.yaml`, ADR-005).

- Arrives: M4.1–M4.5 (Phase 4)
- May depend on: `interfaces` (ports)
