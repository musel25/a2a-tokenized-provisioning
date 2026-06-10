# ADR-003 — Dashboard: optimized for the defense jury

**Status:** accepted · 2026-06-09

## Context
The Streamlit dashboard could serve as an engineering debug console or as the defense
demo's storytelling instrument. These pull the design in opposite directions.

## Decision
Jury-first. Concretely:

- A **narration line** under the lifecycle stepper states, in plain language, what is
  happening now ("Consumer is proving it owns entitlement #7…").
- **Step-through mode** (advance one lifecycle phase per key press) alongside auto-run,
  plus replay/reset.
- The three columns mirror the three trust domains — judgment (agents) / trustless
  settlement (chain) / physical enforcement (network) — so the layout itself argues the
  thesis.
- The bandwidth ↔ telemetry scenario switch stays prominent: same machinery, different
  translator, on screen.
- Events rendered as words; hex addresses truncated; raw component logs exist but
  **collapsed by default**.

## Consequences
- Debugging happens in terminals and log files, not the dashboard — fine, that is where it
  happens anyway during development.
- Wireframe and storyboard live in `docs/08-demo-dashboard.md`.
