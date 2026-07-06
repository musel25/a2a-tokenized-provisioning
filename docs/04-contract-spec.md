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
| **I1** | Only `fulfill` can mint an entitlement | no public mint path; mint is `internal`; `fulfill` is `_issue`'s sole production caller | M1.2 (structural) → **M1.3 (full)** |
| **I2** | Each offer salt is fulfillable exactly once | replay reverts `OfferAlreadyUsed` (`test_I2_*`) | **M1.3** ✓ |
| **I3** | Payment and mint are atomic — both, or neither | revert-rollback proof (no NFT, salt unconsumed, balances intact) | **M1.3** ✓ |
| **I4** | Only the issuer may revoke | non-issuer/owner/stranger `revoke` → `NotIssuer` | **M1.4** ✓ |
| **I5** | Revoke sets a flag, never burns the token | after revoke: `ownerOf` intact, 8 fields identical, one bit changed | **M1.4** ✓ |
| **I6** | Terms in storage are immutable after mint | terms identical before/after an ERC-721 transfer | **M1.2** ✓ |
| **I7** | `tokenURI` is derived purely from storage | exact expected `data:` URI reproduced from the same storage | **M1.4** ✓ |
| **I8** | An expired/revoked entitlement still exists and is readable | 30-day warp: `tokenURI` byte-identical, `ownerOf` intact | **M1.4** ✓ |

### I1 — only `fulfill` mints
**Why.** The ticket is *load-bearing* (story ch. 3): the network's gatekeeper authorizes by
on-chain ownership alone. If anything other than a paid `fulfill` could mint, anyone could
conjure a free entitlement and get service for nothing — the entire payment guarantee leaks.
**How (M1.2).** Enforced *structurally* before `fulfill` even exists: the mint helper
`_issue` is `internal` (callable only from inside the contract), and there is **no** public
`mint`. Tests reach `_issue` only through a `SettlementHarness` (§5). Full behavioural proof
(`fulfill` is the *sole* caller of `_issue`) arrives with `fulfill` at M1.3.

### I2 — each salt single-use · I3 — atomic fulfill  *(landed M1.3)*
**Why.** I2: an offer is one promise; if the same signed blob could be redeemed twice, Bell
would owe two tickets for one quote — replay is theft from the provider. I3: `fulfill` does
six things (check, punch salt, pull payment, mint, two events); if any subset could land
without the rest, you'd get paid-but-no-ticket or ticket-but-no-payment — the exact
stranger-to-stranger failure the settlement exists to kill (story ch. 4).

**How (M1.3).** The ledger is `mapping(bytes32 => bool) consumed`, keyed by the **full
EIP-712 digest** (exactly what the provider's signature covers — one slot per signed
promise; for an honest provider who randomizes salts, per-digest ≡ per-salt). Checks run in
the `FakeChain.fulfill` order — expired → consumer binding → salt → funds — with
`ECDSA.recover` slotted between salt and funds (the fake doesn't verify signatures, so
parity is silent there; after the cheap reverts is also where ecrecover costs least). The
custom errors carry the fake's exception names verbatim: `OfferExpired`, `WrongConsumer`,
`OfferAlreadyUsed`, `BadSignature`.

Proven by `test/Fulfill.t.sol`: replay by the buyer and by a *different* buyer
(`test_I2_*`), the atomicity rollback proofs (`test_I3_noAllowanceRollsBackTheWholeWorld`
asserts salt unpunched + no NFT + balances intact after a mid-`fulfill` revert), one
tamper test per interesting field (any mutation → `BadSignature`), the boundary
`block.timestamp == validUntil` (still valid — the fake's strict `>`), two revert-order
pins, and fuzz over salts/prices. The structural difference rehearsed in the skeleton
holds: the fake earns atomicity by ordering checks before mutations (Python has no
rollback); the contract gets I3 from the EVM — a revert undoes every storage write in the
transaction. `fulfill` still marks `consumed` *before* the external token call
(checks-effects-interactions), so a reentrant replay dies at `OfferAlreadyUsed` rather than
relying on rollback alone.

**Deliberate non-check.** `fulfill` ignores `startTime`/`endTime`: buying before the
window opens is legitimate (Ada buys at 13:45 for 14:00); *using* the window is the
controller's decision at activation, against chain time (ADR-004).

### I4 — only issuer revokes · I5 — revoke is a flag, not a burn  *(landed M1.4)*
**Why.** I4: revocation is the issuer's emergency brake on *his own promise* (ch. 8) — in
Ada's hands it would be meaningless (she can simply not use the ticket), in a stranger's
it would be sabotage. I5: a burned ticket erases the evidence; a flagged one stays a
public record of what was promised and what was withdrawn.

**How (M1.4).** `revoke(id)` gates on `entitlements[id].issuer == msg.sender`
(`NotIssuer` otherwise — which also rejects unminted ids, whose issuer slot is
`address(0)`), sets the one bit, and emits `Revoked(id)` — the event the controller's
watcher will subscribe to (M4.5). Re-revoking succeeds idempotently (parity with
`FakeChain.revoke`; downstream teardown is idempotent, rule 8). Proven by
`test/Revoke.t.sol`: `test_I4_issuerRevokeSetsFlagAndEmits`, `test_I4_ownerCannotRevoke`,
`test_I4_strangerCannotRevoke`, `test_I5_revokeDoesNotBurnOrRewriteTerms` (all eight
fields byte-identical, `ownerOf` intact, exactly one bit changed).

**Expiry, by contrast, is passive** and has *no function at all*: nothing on-chain moves
at 16:00 (`test_I8_expiryIsPassive_chainDoesNothingAt1600` warps 30 days past `endTime`
and asserts `tokenURI` is byte-identical). "Expired" is a reader's judgment against chain
time (ADR-004); *acting* on it is the controller's job.

### I6 — terms immutable after mint  *(this milestone)*
**Why.** A concert ticket whose seat number can be edited after sale is worthless. Ticket
#7's terms (50 Mbps, this path, this window) must mean the same thing for the gatekeeper at
16:00 as at 14:00 — *and* must not change if Ada resells the NFT to someone else. Terms live
in the contract's storage (not a URL that can 404 or be re-edited — ch. 2).
**How.** Mint #7 to Ada with Bell's terms; read `entitlements(7)`; transfer the token to a
third address; read `entitlements(7)` again — **every field identical**; only `ownerOf(7)`
changed. The terms are bound to the token, not to the holder.

### I7 — `tokenURI` is the storage, restated  *(landed M1.4)*
**Why.** The ticket's fine print must share the terms' tamper-proof home: an `https://`
URI is a promise some web server outlives the ticket; a `data:` URI rendered from storage
on every call cannot 404 and cannot lie.
**How.** `tokenURI(id)` string-concats the stored fields into JSON and base64-wraps it
(OZ `Base64`/`Strings`); unminted ids revert via `_requireOwned` (the M1.2 existence
rule). `params` is deliberately omitted (ABI blob; decoders use `entitlements(id)` per
docs/03 §4.2). Proven by `test_I7_tokenURIDerivesPurelyFromStorage` (expected URI rebuilt
from the same storage, byte-equal) and `test_I7_tokenURIReflectsRevocation` (revoke →
rendered JSON flips live).

### I8 — an expired/revoked entitlement still exists  *(complete as of M1.4)*
**Why.** The controller must be able to read *why* it is denying service ("this ticket
expired at 16:00"), which is impossible if expiry deletes the record. v0 keeps every
entitlement permanently readable.
**How.** M1.2 made storage permanent (`entitlements(id)` always returns). M1.4 proves the
two death modes leave it intact: `vm.warp` 30 days past `endTime` → everything
byte-identical (expiry is passive); revoke → one bit flips, owner and terms remain
(`test_I5_…`, `test_I8_…`).

---

## 4. Built so far (the milestone ledger)

**M1.2 — storage + ownership.** `A2ASettlement is ERC721`, the eight-field `Entitlement`
struct *exactly* per `docs/03 §2.2`, a `mapping(uint256 => Entitlement) public
entitlements`, and `_issue(...) internal` that mints to the owner, stores the terms
verbatim, and hands back an incrementing id. Tests named after the invariants
(`test_I6_...`). At this point the contract could *hold* a correct ticket but not be
*bought* — the only way to create #7 was the test harness (I1 by construction).

**M1.3 — the purchase (I1 complete, I2, I3).** The `Offer` struct (twelve fields, exactly
`docs/03 §1.4`), `OFFER_TYPEHASH` + `hashOffer` under the pinned domain
(`"A2AProvisioning"`, `"0"` — `docs/03 §2.1`), the `consumed` digest ledger, `MockTOK`
(open-faucet ERC-20), and `fulfill` itself: verify → pull payment → mint → events, in one
transaction. I1 is now *behavioral*, not just structural: `fulfill` is `_issue`'s sole
production caller, and `test/Fulfill.t.sol` exercises the production contract with no
harness at all.

**M1.4 — the rest of the ticket's life (I4, I5, I7, I8 complete).** `revoke` (issuer-only
flag + `Revoked` event), on-chain `tokenURI` (base64 `data:` JSON rendered from storage),
and the real `script/Deploy.s.sol` → `contracts/deployments/anvil.json` (+ `just
deploy-local`). All eight invariants now have green tests next to them.

**Explicitly *not* built yet (scope border in ink):**
- Any Python client / cross-stack signature → **M1.5**.

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
