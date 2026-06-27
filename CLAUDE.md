# CLAUDE.md — rules for this repository

Agent-to-agent tokenized network-service provisioning: AI agents buy network services
(bandwidth, telemetry) from each other; payment is atomically exchanged for an ERC-721
entitlement; a deterministic controller honors the entitlement by configuring real
SR Linux routers via gNMI.

**Read first, in order:** `docs/00-the-story.md` (concepts) →
`docs/03-interfaces.md` (schemas) → `docs/01-implementation-plan.md` (current milestone)
→ `docs/adr/` (decisions). `DESIGN.md` is the full formal plan.

## Hard rules (violating any of these is a wrong answer, even if the code works)

1. **The controller and its predicate are never an LLM** and never call one. Authorization
   is deterministic code. LLM judgment exists in exactly two places: the consumer's
   accept/reject decision and the provider's quote/decline decision.
2. **Private keys live only in `chainmcp`.** No other package reads, receives, stores, or
   logs a key. The controller verifies signatures; it never signs.
3. **Cross-package data shapes come only from `a2a_interfaces`.** Never redefine a payload
   locally. Changing a shape = bump its `v` + update `docs/03-interfaces.md` in the same
   commit.
4. **Controller domain code (`controller/.../domain.py`) imports no I/O** — no web3, no
   pygnmi, no HTTP, no filesystem. It depends on the Protocols in `a2a_interfaces.ports`.
   Adapters live at the edges.
5. **Chain time is the only clock for validity** (ADR-004). OS timers may schedule
   wake-ups; every action re-checks `chain_time()` before executing.
6. **`netctl` is topology-agnostic.** It receives concrete device/interface names
   (`ResolvedPath`/`ResolvedNode`) and speaks gNMI. The `resourceId → topology` map lives
   only in `controller/resource_map.yaml` (ADR-005).
7. **Mocks implement the same Protocol as real adapters** and pass the same shared
   contract-test suite. A mock with different behavior at the port is a bug.
8. **Teardown is idempotent** everywhere. Calling it twice is a success, not an error.
9. **No new abstraction with a single implementation.** Duplicate a small struct before
   coupling two packages.
10. **Evidence or it didn't happen.** Every milestone ends with tests green and
    `docs/evidence/M<id>.md` updated. Commit messages start with the milestone id.

## Package map (import direction: downward only)

| Package | Job | May depend on |
|---|---|---|
| `interfaces` | shapes + ports (pydantic, Protocols) | — |
| `contracts` | Solidity settlement (Foundry) | — |
| `chainmcp` | chain adapter + signing + MCP server; the only key holder | interfaces, contracts ABI |
| `netlab` | Containerlab topology + manual recipes | — |
| `netctl` | gNMI provisioner lib (+ debug MCP) | interfaces |
| `controller` | predicate, state machine, auth, translators, HTTP API | interfaces (ports) |
| `agents` | LangGraph graphs, LLM client, MCP clients, A2A adapters | interfaces |
| `e2e` | skeleton, lifecycle tests, bring-up, dashboard | everything |

## Conventions

- Python: uv workspace at root (`uv sync`, `uv run pytest`), pydantic v2, ruff. Tests live
  in each package's `tests/`.
- Solidity: Foundry; OpenZeppelin via `forge install`; solc pinned in `foundry.toml`;
  tests named after invariants (`test_I2_offerSingleUse`). EIP-712 domain:
  `("A2AProvisioning", "0", 31337, <settlement>)` — must match `docs/03` §2.1 and the
  Python signer byte-for-byte.
- LLM access only via the OpenAI-compatible client configured by `LLM_BASE_URL` /
  `LLM_MODEL` / `LLM_API_KEY` (ADR-001). Never import a backend-specific SDK in `agents`.
- A2A SDK imports confined to `agents/*/a2a_adapter.py`, version pinned (ADR-002).
- Skeleton profiles: `SKELETON_PROFILE = mock | chain | chain+net | full`. CI runs `mock`
  + unit + Foundry tests. Real profiles run locally and must clean up after failures
  (fixture finalizers).
- Commands: `just up` / `just down` (Phase 6), `just deploy-local`,
  `sudo containerlab deploy -t netlab/topology.clab.yml`.
- Canonical example values (Ada/Bell/ticket #7/10 TOK/50 Mbps) come from
  `a2a_interfaces.fixtures` — story, docs, and tests share them; change them in one place
  or not at all. Prose/schemas may *quote* these values but never introduce a divergent one.
- Writing standard: comments and docs follow `docs/04-writing-standard.md` — comments say
  what the code can't (decision/boundary/subtlety/pre-empted mistake), never restate it;
  docs build motivation→idea→mechanism, grounded in the canonical example. Each milestone's
  evidence checklist asserts the slice meets `docs/04`.
- Plan-of-record: `docs/01-implementation-plan.md` (milestone map; order is *not* numeric:
  M0.1 → M1.1 → M0.2 → M0.3 → M1.2 …) + per-milestone `docs/evidence/M<id>.md`. There is no
  `PLAN.md`; the `/slice` skill's PLAN.md steps map onto the evidence file instead.

## When asked to "just make it work"

Prefer the smallest change that keeps every rule above. If a rule blocks the task, say so
and propose the rule-respecting alternative instead of silently violating it. The human is
optimizing for understanding: explain non-obvious choices in the PR/commit description.
