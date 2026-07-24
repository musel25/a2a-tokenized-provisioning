# The course, v2 — rebuild the project from zero, one robbery at a time

Ten notebooks for a **complete beginner** — no Python-typing lore, no blockchain
background, no networking experience assumed. The goal: understand this project deeply
enough to *write the paper about it*.

## The method: rebuild, then reveal

The v1 course imported the real repo code and inspected it (`inspect.getsource`
everywhere). That's backwards for a beginner: you end up reading production code with
all its edge cases before you understand the problem it solves. v2 inverts it — every
notebook follows the same rhythm:

1. **A problem, told as a story.** Always Ada and Bell (50 Mbps, 14:00–16:00, 10 TOK,
   ticket #7 — the repo's canonical example).
2. **Rebuild the solution from scratch, in the notebook.** Plain Python, written cell by
   cell, where every field and every `if` is added *because you just watched its absence
   get exploited*. The architectural decisions are re-derived, not quoted.
3. **Reveal — and run — the real thing.** A mapping table (your toy → the real module),
   the production code quoted as prose where it earns it, and then the *actual*
   component run live on the same canonical example, answering with the same behavior
   your toy invented.

Exercises are embedded where each concept lands: **✏️ Your turn** — a scaffold cell you
edit, a prediction you write down first, and a fold-out solution. No self-grading
asserts; you check yourself against the solution.

## The path

| # | Notebook | You rebuild from scratch | The real thing you then run | Status |
|---|---|---|---|---|
| 00 | The problem | a naive Ada↔Bell trade; watch it fail three ways | the story, the four trust domains | planned |
| 01 | Machines that can't lie | a toy ledger → why append-only → keys and addresses | a disposable Anvil chain | planned |
| 02 | Speaking precisely | a deal as a dict → typos → a validated `Offer` shape | `a2a_interfaces` + the canonical fixtures | planned |
| 03 | The atomic swap | the settlement vending machine, robbery by robbery | `Settlement.sol` live: fulfill, replay-deny, revoke | **pilot — done** |
| 04 | Signatures that contracts believe | sign a dict, break it, re-derive EIP-712 by hand | `chainmcp` signing vs the contract's digest | planned |
| 05 | The bouncer | the predicate, check by check, attack by attack | the real `controller` domain + HTTP API | planned |
| 06 | The hands | "configure a router" as a toy; idempotent teardown; the resource map | `netctl` against the mock (lab optional) | planned |
| 07 | The brains | a minimal agent loop; judgment in exactly two places | the LangGraph agents on a stub LLM | planned |
| 08 | The whole play | compose *your own toys* 01–07 into the full lifecycle + revocation | the real skeleton, mock profile, side by side | planned |
| 09 | Did it work? | the seven evaluation questions as a paper-reviewer's objections | headline numbers recomputed from the committed dataset | planned |

Read them in order: each assumes everything before it and nothing after it.

## How to run

```bash
uv sync --all-packages          # once
forge build --root contracts    # once — enables the live-chain sections (03, 04, 08)
```

Open a notebook, pick the `.venv` kernel, run top to bottom. Every notebook runs green
headless with **no infrastructure**: cells that want a live chain detect its absence,
say what to install, and skip.

```bash
uv run --group demo jupyter nbconvert --to notebook --execute --stdout \
    e2e/notebooks/course/03_the_atomic_swap.ipynb > /dev/null
```

## Relation to the other learning surfaces

- **This course** — the from-zero spine. Start here.
- **The explore notebooks** (`e2e/notebooks/*_explore.ipynb`) — per-component tours at
  working-engineer altitude, for after the corresponding chapter.
- **The scratch bench** (`e2e/notebooks/scratch_inspect.ipynb`) — pre-wired imports,
  playground-empty. Your own questions go there.
- **The cast labs** (`contracts/EXPLORE*.md`) — the Solidity surface from a terminal.
- **The docs route** — [`docs/LEARNING-PATH.md`](../../../docs/LEARNING-PATH.md).
