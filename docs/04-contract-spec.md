# 04 — Contract spec: the settlement invariants (Phase 1)

> **Status:** living. Opened at the start of Phase 1 (M1.2); filled in as M1.2 → M1.3 → M1.4
> land. An invariant here without a green Foundry test next to it is a *claim*, not a fact.
> **Companions:** `docs/03-interfaces.md` §2 (the on-chain shapes this protects) ·
> `docs/01-implementation-plan.md` Phase 1 (the milestone order) · `CLAUDE.md` (the hard rules).
> *(Numbering note: `docs/04-writing-standard.md` also starts with "04"; the plan-of-record
> named this file, so both coexist. Renumber later if it grates — not in a code slice.)*

---

## 1. Why we write the invariants before the contract

The settlement contract is the one place in the whole system where **money and the ticket
change hands in the same breath**. It runs on a public chain: once deployed there is no
admin button, no "undo", no patch Tuesday. A logic bug is not a bad afternoon — it is funds
gone or a ticket minted that someone can enforce forever.

So we do not start by writing code and testing a few happy paths. We start by naming the
properties that must hold **for every possible input** — an *invariant* (a statement that is
true no matter what arguments, in what order, by whom). Each invariant becomes at least one
test. The tests are the real specification; this document is their index and their *why*.
Code comes last, and only has to make already-written tests go green.

This is the "spec-first" milestones in `docs/01`: **spec → tests → code**, never the reverse.

---

## 2. The canonical example (one source of truth)

Every invariant below is cashed out in the same story, whose values come from exactly one
place, `a2a_interfaces.fixtures` (never retyped with a different number — `CLAUDE.md`):

> **Ada** (`0xf39F…2266`) buys **ticket #7** from **Bell** (`0x70997970…79C8`): *bandwidth,
> up to 50 Mbps, path resource `0x…0007`, window 14:00→16:00, for 10 TOK.* The moment she
> pays, entitlement #7 is **minted** (created as a new token) to Ada, its terms frozen in
> the contract's own storage, its owner readable by anyone via `ownerOf(7)`.

"Mint" = the ERC-721 word for *bring a brand-new token into existence and assign its first
owner*. ERC-721 = the Ethereum standard for a registry of unique tokens (story ch. 2: a land
registry, not monkey JPEGs); we inherit OpenZeppelin's audited implementation for the
ownership bookkeeping and add only what is ours — the `Entitlement` terms.

---

## 3. The eight invariants

| Id | Invariant (must always hold) | Proven by | Lands |
|----|------------------------------|-----------|-------|
| **I1** | Only `fulfill` can mint an entitlement | no public mint path; mint is `internal` | M1.2 (structural) → M1.3 (full) |
| **I2** | Each offer salt is fulfillable exactly once | replay reverts `OfferAlreadyUsed` | M1.3 |
| **I3** | Payment and mint are atomic — both, or neither | revert-rollback proof (no NFT, salt unconsumed) | M1.3 |
| **I4** | Only the issuer may revoke | non-issuer `revoke` reverts | M1.4 |
| **I5** | Revoke sets a flag, never burns the token | after revoke, `ownerOf` still returns the owner | M1.4 |
| **I6** | Terms in storage are immutable after mint | terms identical before/after an ERC-721 transfer | **M1.2** |
| **I7** | `tokenURI` is derived purely from storage | rendered JSON matches stored fields | M1.4 |
| **I8** | An expired/revoked entitlement still exists and is readable | `entitlements(id)` returns after expiry/revoke | M1.2 (readable) → M1.4 (expiry/revoke) |

### I1 — only `fulfill` mints
**Why.** The ticket is *load-bearing* (story ch. 3): the network's gatekeeper authorizes by
on-chain ownership alone. If anything other than a paid `fulfill` could mint, anyone could
conjure a free entitlement and get service for nothing — the entire payment guarantee leaks.
**How (M1.2).** Enforced *structurally* before `fulfill` even exists: the mint helper
`_issue` is `internal` (callable only from inside the contract), and there is **no** public
`mint`. Tests reach `_issue` only through a `SettlementHarness` (§5). Full behavioural proof
(`fulfill` is the *sole* caller of `_issue`) arrives with `fulfill` at M1.3.

### I2 — each salt single-use · I3 — atomic fulfill
Deferred to **M1.3** (this is story ch. 4, the vending machine). Listed here so the spec is
whole; `fulfill`, the salt ledger, and the atomic `transferFrom`+mint do not exist yet.

Already *rehearsed*, though: since the post-M0.3 review hardening, the skeleton's
`FakeChain.fulfill` checks in the contract's planned revert order — expired → consumer
binding → salt → funds — before any mutation, and `e2e/tests/test_lifecycle.py` carries one
deny-path test per check, each asserting the world is left untouched (I3 in cardboard).
Those tests are the parity spec M1.3's Foundry revert tests must match, check for check.
The one structural difference to keep in mind when writing the Solidity: the fake needs
checks-before-mutation because Python has no rollback; the contract gets I3 from the EVM —
a revert undoes every storage write in the transaction, whatever the order.

### I4 — only issuer revokes · I5 — revoke is a flag, not a burn
Deferred to **M1.4**. Note already for then (ch. 8): expiry is *passive* (the chain does
nothing at 16:00), revocation is *active* and stays a flag so the token — and its history —
remain readable.

### I6 — terms immutable after mint  *(this milestone)*
**Why.** A concert ticket whose seat number can be edited after sale is worthless. Ticket
#7's terms (50 Mbps, this path, this window) must mean the same thing for the gatekeeper at
16:00 as at 14:00 — *and* must not change if Ada resells the NFT to someone else. Terms live
in the contract's storage (not a URL that can 404 or be re-edited — ch. 2).
**How.** Mint #7 to Ada with Bell's terms; read `entitlements(7)`; transfer the token to a
third address; read `entitlements(7)` again — **every field identical**; only `ownerOf(7)`
changed. The terms are bound to the token, not to the holder.

### I8 — an expired/revoked entitlement still exists  *(readability this milestone)*
**Why.** The controller must be able to read *why* it is denying service ("this ticket
expired at 16:00"), which is impossible if expiry deletes the record. v0 keeps every
entitlement permanently readable.
**How (M1.2).** Storage exists and `entitlements(id)` returns the full struct for any minted
id. The *expiry* and *revoked* semantics that I8 ultimately guards arrive with `vm.warp`
time-travel tests and `revoke` at M1.4.

---

## 4. This milestone (M1.2): storage + ownership

**Built:** `A2ASettlement is ERC721`, the eight-field `Entitlement` struct *exactly* per
`docs/03 §2.2`, a `mapping(uint256 => Entitlement) public entitlements`, and
`_issue(...) internal` that mints to the owner, stores the terms verbatim, and hands back an
incrementing id. Tests named after the invariants above (`test_I6_...`, `test_I1_...`).

**Explicitly *not* built here (scope border in ink):**
- `fulfill`, EIP-712 signature recovery, the salt ledger, payment → **M1.3** (I2, I3).
- `revoke`, events, `tokenURI`, the deploy script → **M1.4** (I4, I5, I7).
- Any Python client / cross-stack signature → **M1.5**.

So in M1.2 the contract can *hold* a correct ticket but cannot yet be *bought*: the only way
to create #7 is the test harness, never a public transaction. That is I1, enforced by
construction two milestones before the real buyer exists.

---

## 5. The harness pattern (why `_issue` is `internal`)

A newcomer's instinct is a `function mintForTest(...) public` so tests can create tickets.
That would be a **standing violation of I1** baked into production code — a public mint path
shipped to the chain forever, exactly the thing I1 forbids.

Instead, the mint helper stays `internal`, and a **test-only** `SettlementHarness` (in
`test/`, never deployed) inherits the contract and exposes a thin `exposed_issue(...)` that
forwards to `_issue`. The superpower lives in the test build; the production contract has no
backdoor. This is the standard Foundry "harness" pattern, and it is *why* the invariant can
be true today: there is genuinely no public way to mint.

---

*Change protocol (CLAUDE.md rule 3): the `Entitlement` shape is owned by `docs/03 §2.2`. To
change a field, bump `docs/03`'s `v`, update this spec, and re-green every `test_I*` in the
same commit.*
