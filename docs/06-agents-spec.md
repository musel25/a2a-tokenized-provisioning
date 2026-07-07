# 06 — Agents spec: where judgment lives (Phase 5)

> **Status:** living — opened at the start of Phase 5, filled in as M5.1 → M5.6 land.
> **Companions:** `docs/03-interfaces.md` §1 (A2A layer), §6 (MCP tools) ·
> `docs/adr/001-llm-serving.md` (the LLM endpoint) · ADR-002 (A2A SDK) · story ch. 9 ·
> `CLAUDE.md` rules 1, 2.

---

## 1. The one principle: judgment in exactly two slots

Everything the *network* does is deterministic and replayable — contracts, controller,
provisioner. The LLM enters in **exactly two places** (rule 1), and nowhere else:

| Slot | Agent | Output shape | File |
|---|---|---|---|
| accept / reject an offer | consumer | `DecisionOutput` | `agents/decision.py` |
| quote / decline (pricing) | provider | `QuoteDecision` → `SignedOffer` or `Decline` | `agents/provider_graph.py` |

Admission control (no-overselling) is **not** a judgment — it is arithmetic over a
capacity ledger, deterministic and reproducible (story ch. 8). The controller's
authorization is likewise deterministic (docs/05). The LLM decides only *whether a deal
happens and at what price*.

## 2. The LLM client (M5.1, ADR-001)

`LLMClient.structured(system, user, schema)` talks to any OpenAI-compatible endpoint and
**always validates the reply against a pydantic model, retrying** until it parses or the
budget is spent — then a clean `StructuredError`, mapped by callers to a safe default
(decline/reject). This guard is what makes the backend irrelevant: the same test passes
against Ollama, vLLM, or a stub. Config is three env vars (`LLM_BASE_URL` / `LLM_MODEL`
/ `LLM_API_KEY`); no backend-specific SDK is imported anywhere in `agents`.

Reply cleaning tolerates what small local models emit: ```json fences and qwen3's
`<think>…</think>` blocks are stripped, then the first balanced `{…}` is validated.

## 3. The consumer graph (M5.2)

LangGraph: `discover → request_quote → decide → settle → activate → report`. Tools are
injected callables (a Protocol) — plain stubs in M5.2, MCP-backed at M5.4, so the graph
never changes. The `decide` node is the LLM slot; an `accept` runs the full purchase, a
`decline` exits gracefully having bought nothing.

## 4. The provider graph (M5.3)

`receive need → admit → quote`. `admit` is the deterministic `CapacityLedger`
(per-window reservations, all-or-nothing — the overselling guard); over capacity yields
an immediate `Decline` with no LLM asked. `quote` is the LLM slot: price the offer or
decline for business reasons (a business decline releases the tentatively-reserved
slot). What crosses the A2A wire is a `SignedOffer` or a `Decline` (docs/03 §1.2).

## 5. MCP servers (M5.4) — *lands with M5.4*

## 6. A2A discovery (M5.5) — *lands with M5.5*

## 7. Skeleton v4 (M5.6) — *lands with M5.6*

---

## Appendix: version pins (ADR-002)

Pinned when each SDK first lands, checked against current docs at that moment (not
memory). `openai` (M5.1), `langgraph` (M5.2), `mcp` (M5.4), `a2a-sdk` (M5.5).
