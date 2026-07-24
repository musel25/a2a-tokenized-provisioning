# The course, v2 — rebuild the project from zero, so you can write the paper

Ten-ish notebooks for a **complete beginner** — no Python-typing lore, no blockchain
background, no networking experience assumed. The goal is not encyclopedic understanding
of the repo: it is understanding **calibrated for writing the full-length paper** — the
decisions and their alternatives, the mechanisms deep enough to defend in review, and an
honest map of what was simplified and why.

## The method: rebuild, then reveal — then claim

The v1 course imported the real repo code and inspected it (`inspect.getsource`
everywhere). That's backwards for a beginner: you end up reading production code with
all its edge cases before you understand the problem it solves. v2 inverts it — every
notebook follows the same rhythm:

1. **A problem, told as a story.** Always Ada and Bell (50 Mbps, 14:00–16:00, 10 TOK,
   ticket #7 — the repo's canonical example).
2. **Rebuild the solution from scratch, in the notebook.** Plain Python, written cell by
   cell, where every field and every `if` is added *because you just watched its absence
   get exploited*. Where the topic is a skill (deploying an agent), this step is a
   genuine from-zero tutorial, before any project code appears.
3. **Reveal — and run — the real thing.** A mapping table (your toy → the real module),
   the production code quoted as prose where it earns it, then the *actual* component
   run live on the same canonical example.
4. **Claim it for the paper.** Two conventions carry the paper focus:
   - **🧭 Decision boxes**, inline at the moment a choice is made, in two honest
     registers. *Principled*: the alternatives fail for an arguable reason — this is
     Design-section material. *Pragmatic*: alternatives exist and may be better in
     production; we took the simplest thing that demonstrates the mechanism — this is
     Limitations-section material, stated plainly, never oversold.
   - **📝 For the paper**, the closing section: draft claim-sentences paired with the
     evidence you personally ran, the reviewer objections you can now answer, and the
     honesty inventory for Limitations.

Exercises are embedded where each concept lands: **✏️ Your turn** — a scaffold cell you
edit, a prediction you write down first, and a fold-out solution. No self-grading
asserts; you check yourself against the solution.

## The path

| # | Notebook | You rebuild / do from scratch | The real thing you then run | Status |
|---|---|---|---|---|
| 00 | The problem | a naive Ada↔Bell trade; watch it fail three ways; the paper's claim stated | the story, the four trust domains | planned |
| 01 | Ledgers, keys, shapes *(deliberately light)* | a toy ledger; keys→addresses; a dict → a validated `Offer` | a disposable Anvil chain; `a2a_interfaces` fixtures | planned |
| 03 | The atomic swap | the settlement vending machine, robbery by robbery | `Settlement.sol` live: fulfill, replay-deny, revoke | **pilot — done** |
| 04 | Signatures that contracts believe | sign a dict, break it, re-derive EIP-712 by hand | `chainmcp` signing vs the contract's digest | planned |
| 05 | The bouncer | the predicate, check by check, attack by attack | the real `controller` domain + HTTP API | planned |
| 06 | The hands *(light)* | "configure a router" as a toy; idempotent teardown; the resource map | `netctl` against the mock (lab optional) | planned |
| 07a | Deploy an agent from zero | the pure tutorial: an LLM call → a hand-written tool loop → the same agent in LangGraph | a stub LLM (endpoint optional) | planned |
| 07b | This project's agents | adapt 07a to the marketplace: judgment in exactly two places | the repo's LangGraph agents, A2A + MCP | planned |
| 08 | The whole play | compose *your own toys* into the full lifecycle + revocation | the real skeleton, mock profile, side by side | planned |
| 09 | Did it work? | the seven evaluation questions as a reviewer's objections | headline numbers recomputed from the committed dataset | planned |
| 10 | The paper | — (the capstone assembles, it doesn't rebuild) | every claim → its notebook → its ADR → its live-recomputed number: the writing map | planned |

(Chapter 02 was merged into 01 — the mechanics there matter less for the paper than the
decisions elsewhere; 03 keeps its number so the pilot's identity is stable.)

Read them in order: each assumes everything before it and nothing after it.

## How to run

```bash
uv sync --all-packages          # once
forge build --root contracts    # once — enables the live-chain sections
```

Open a notebook, pick the `.venv` kernel, run top to bottom. Every notebook runs green
headless with **no infrastructure**: cells that want a live chain (or an LLM endpoint)
detect its absence, say what to install, and skip.

```bash
uv run --group demo jupyter nbconvert --to notebook --execute --stdout \
    e2e/notebooks/course/03_the_atomic_swap.ipynb > /dev/null
```

## Relation to the other learning surfaces

- **This course** — the from-zero spine, aimed at the paper. Start here.
- **The explore notebooks** (`e2e/notebooks/*_explore.ipynb`) — per-component tours at
  working-engineer altitude, for after the corresponding chapter.
- **The scratch bench** (`e2e/notebooks/scratch_inspect.ipynb`) — pre-wired imports,
  playground-empty. Your own questions go there.
- **The cast labs** (`contracts/EXPLORE*.md`) — the Solidity surface from a terminal.
- **The docs route** — [`docs/LEARNING-PATH.md`](../../../docs/LEARNING-PATH.md); the
  ADRs in `docs/adr/` are the decision boxes' primary sources.
