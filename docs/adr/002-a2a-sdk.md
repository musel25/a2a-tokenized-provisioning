# ADR-002 — Agent-to-agent layer: official A2A SDK

**Status:** accepted · 2026-06-09

## Context
Agents must discover each other and exchange offers. Options: the official A2A protocol SDK
(`a2a-sdk`, Linux Foundation), or custom JSON-over-HTTP shaped like A2A.

## Decision
Use the **official A2A SDK**, version pinned. Providers run A2A servers publishing agent
cards (well-known path) with skills `quote_bandwidth` / `quote_telemetry`; the consumer is
an A2A client. Our domain payloads (`ServiceNeed`, `SignedOffer` — defined in
`docs/03-interfaces.md`) ride as structured **data parts inside A2A messages**: the SDK is
the envelope, never the schema.

All SDK imports are confined to one adapter module per agent (`agents/*/a2a_adapter.py`).
The rest of the agent code sees only our domain payloads.

## Consequences
- Thesis claim upgrades from "custom messages" to "implements the open A2A protocol";
  discovery via agent cards comes free.
- The spec is young and moves: pin the version, isolate imports, re-check SDK docs at
  Phase 6 before writing the adapters.
- We adopt A2A concepts (cards, tasks, messages) minimally — only what discovery + quoting
  needs.
