# 04 — Writing standard: comments and docs

> **Status:** living. The bar every comment, docstring, and doc in this repo is held to.
> It exists because "the code works" is not the goal here — *understanding* is (CLAUDE.md).
> A reader six months from now (often you) should be carried, never dumped.
> **Companions:** `CLAUDE.md` (the hard rules) · `docs/02-architecture.md` (the module view) ·
> `docs/evidence/TEMPLATE.md` (the per-milestone gate).

This standard is derived from the repo's own best passages, not generic advice. Every rule
below points at a real line you can open and imitate.

---

## 1. The one test: does it say what the code cannot?

A comment earns its place only by adding what the reader cannot get from the code itself.
The code already says *what* it does. A good comment says one of four things the code can't:

- **the decision** — why this and not the obvious alternative;
- **the boundary** — which rule/ADR this line protects, and what must *not* leak across it;
- **the subtlety** — a non-obvious invariant, ordering, or unit;
- **the pre-empted mistake** — the "improvement" a newcomer would wrongly attempt.

The anchor for the whole standard — `interfaces/src/a2a_interfaces/models.py`:

```python
# 0x-prefixed hex. We validate the *pattern* only; EIP-55 checksum verification
# needs keccak and therefore belongs to chainmcp, not here.
Address = Annotated[str, StringConstraints(pattern=r"^0x[0-9a-fA-F]{40}$")]
```

In three lines it states the decision (pattern-only), the boundary (keccak lives in
`chainmcp`, rule 2/4), and the mistake it heads off (don't add checksum validation here).
Aspire to this shape: **decision + boundary + gotcha.**

If a comment only restates the code, **delete it.** A wrong comment is worse than none —
during M0.2 a comment claimed `docs/03 §2.1` said "eleven fields" *after* §2.1 was fixed to
"twelve"; it actively misled until caught. Comments are code: when the fact changes, the
comment changes in the same commit, or it goes.

### Banned (these read as machine-generated)

- Restating the line: `# import json`, `# increment i`, `# loop over items`.
- Filler labels that echo the name: `# lint` above a recipe named `lint`. (If a label must
  exist — e.g. a `just` recipe doc — make it carry information: `# ruff lint (rules in pyproject)`.)
- AI hedging tells: `Note that…`, `Here we…`, `It's worth mentioning`, `In summary`, `Let's…`.
- Decorative banners with no content. A banner is allowed **only** if it carries a section
  citation, e.g. `# --- enums (docs/03 §3.3) ---` — that earns its keep; `# --- helpers ---`
  does not.

### When NOT to comment

Self-evident code with a descriptive name needs nothing. `ResolvedNode` (one field,
`device: str`) is clearer without a docstring than with a decorative one. Over-commenting
the obvious is the same noise as filler — it just looks busier.

---

## 2. Docs: motivation → idea → mechanism, grounded in numbers

Prose docs (`docs/00`, `02`, ADRs, evidence) carry a heavier burden than comments: they
*teach*. Three rules.

**Order every section motivation → idea → mechanism.** Introduce a concept by the problem
it solves, before naming it. The model — `docs/00-the-story.md`:

> Ada does the arithmetic. 45 GB in two hours requires a steady **50 Mbps** (50 Mbps ×
> 7,200 s = 360 billion bits = 45 GB — exactly).

The number `50 Mbps` is *derived from a real job*, not asserted. The reader feels why it
must be 50 before the word "bandwidth" is technical.

**Cash out every abstraction in the canonical example.** The shared cast is Ada (consumer,
`0xf39F…2266`), Bell (provider, `0x7099…79C8`), ticket **#7**, 50 Mbps, 10 TOK — and these
values live in exactly one place, `a2a_interfaces.fixtures` (see §3). A paragraph that says
"the provider signs an offer for some bandwidth" is weaker than "Bell signs 50 Mbps on path
A→B for 10 TOK, minting ticket #7 to Ada." Prefer the second, always.

**Draw scope borders in ink.** Say what is *not* built, *not* solved, still a stub. The
model — `docs/00` Chapter 8's trustless-vs-assumed table, and `docs/02` §6 "What is NOT
here yet". A doc that only describes the finished system lies about the present.

---

## 3. One canonical example, one source

The failure mode this repo is most prone to is **drift**: the same example, restated by
hand in five files, quietly disagreeing. (M0.2's audit found ticket #7's validity window
stamped with two different epochs across the story and `docs/03`.)

The rule: **numeric and address values for the canonical example come from
`a2a_interfaces.fixtures`.** Prose and schemas may *quote* them; they may never introduce a
divergent value. When a doc needs the offer, it shows the fixture values (Bell `0x7099…`,
token `0x5FbD…`, `resourceId 0x…0007`, 10 TOK), and ideally points back to `fixtures` as
the source. Change them in one place or not at all (CLAUDE.md).

---

## 4. Per-artifact shape

**Code module docstring** — what the file is, why it exists, the one or two conventions a
reader must know. Model: `models.py` header (frozen shapes, no I/O, naming split).

**Test** — name states the invariant; a one-line docstring or the module docstring states
*why the invariant matters*. A trivial/no-op test must justify its existence and name its
sunset. Model: `e2e/tests/test_stage_exists.py` ("proves the workspace wiring before any
real code exists … replaced in spirit by the lifecycle tests at M0.3").

**ADR** — Context → Decision → Consequences. The Context must **name each rejected
alternative with its reason inline**, not merely state the constraint. Model: ADR-005
("Candidates: the contract (too rigid, leaks topology on-chain), `netctl` (couples gNMI to
one lab), or the controller").

**Evidence file** — paste **real** command output (run ids, durations, counts), an honest
"surprises/deviations" section, a checklist whose green marks are each backed by pasted
proof. Any block that is reformatted rather than literally pasted must be labeled
`(reconstructed)`. Model: `docs/evidence/M0.1.md`.

**README stub** — job → constraining rule/ADR (by number) → arrival milestone → what it may
depend on. Model: `agents/README.md`.

**Config (Justfile, ci.yml, pyproject, foundry.toml)** — comment only the non-obvious: a
pinned version's *reason*, a step that exists for a subtle purpose. Model:
`foundry.toml` (`solc = "0.8.30" # pinned (CLAUDE.md): same compiler everywhere, forever`).

---

## 5. The gate

This standard is enforced per slice, not in a sweep. Add one line to each milestone's
`docs/evidence/M<id>.md` done-checklist:

> - [ ] Comments & docs meet `docs/04`; any canonical values match `a2a_interfaces.fixtures`.

When that box is honestly checkable, the milestone keeps the bar. When it isn't, the
milestone isn't done — same discipline as "evidence or it didn't happen."
