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

## 5. MCP servers (M5.4)

Each agent runs its own `chainmcp` instance (its key); the graph reaches the chain only
through `chain_tools(client)` callables (the §6.1 operations) or the FastMCP shell
`build_chain_mcp(client)` for cross-process agents. `ChainConsumerTools`/
`ChainProviderTools` implement the graphs' Protocols, so stubs → real is a zero-graph-code
swap. `ctrl-mcp` is the consumer tool's three HTTP calls to the M4.4 controller.

## 6. A2A discovery (M5.5)

The a2a SDK is confined to `a2a_adapter.py` (ADR-002, pinned `a2a-sdk==0.3.26` — the
JSON-card 0.3.x line, not the protobuf 1.x rewrite). Provider cards carry one `quote_*`
skill; `registry.json` lists them. Domain payloads travel as JSON data parts. Integrity
is inherited, not added: a tampered offer in transit dies at the contract's
`BadSignature` (M1.3).

## 7. Skeleton v4 (M5.6)

The `full` profile: the real consumer and provider graphs drive the lifecycle against
real chainmcp tools, a real controller, and real Anvil state — the skeleton test is now
the system test. Because judgment is nondeterministic, the tests assert VALID BEHAVIOR
(schema + invariants), branching on accept/decline, not one fixed path. A deterministic
variant (controllable fake LLM) proves the wiring in CI; an opt-in `A2A_LIVE_LLM=1`
variant drives the same graphs with real judgment on a fast model.

---

## Appendix: version pins (ADR-002)

Pinned when each SDK first lands, checked against current docs at that moment (not
memory). `openai` (M5.1), `langgraph` (M5.2), `mcp` (M5.4), `a2a-sdk` (M5.5).
