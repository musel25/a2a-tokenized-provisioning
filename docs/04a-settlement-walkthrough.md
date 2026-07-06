# 04a — Settlement, for a complete beginner: what the contract *is* and why

> **The one-sentence answer:** `A2ASettlement` is a program that lives on a blockchain and
> acts as the **public, tamper-proof registry of service "tickets"** — for every ticket it
> records *what it grants* and *who owns it*, so a network gatekeeper can later trust the
> answer to "does Ada own a valid 50 Mbps ticket?" — and (since M1.3) it is also the
> **cashier**: the one function that sells a ticket, `fulfill`, takes the payment and mints
> the ticket in a single indivisible step.
>
> **Audience:** never written Solidity. Every term is glossed on first use. The runnable
> companions are [`contracts/EXPLORE-settlement.md`](../contracts/EXPLORE-settlement.md)
> (storage + ownership) and [`contracts/EXPLORE-fulfill.md`](../contracts/EXPLORE-fulfill.md)
> (the purchase, and four ways to fail it); the terse invariant list is
> [`docs/04-contract-spec.md`](04-contract-spec.md); the code is
> [`contracts/src/Settlement.sol`](../contracts/src/Settlement.sol).

---

## 1. First — what is a "smart contract" at all?

A **smart contract** is a small program that you upload (*deploy*) onto a blockchain. Once
there, three properties make it unlike a normal program:

- **Its code can't be changed** — not by you, not by Bell, not by anyone. What you deployed
  is what runs, forever.
- **It has its own memory that lives on the chain** (called *storage*) — a notebook bolted
  inside it whose contents persist between uses and are visible to everybody.
- **Anyone can call its functions.** A call that only *reads* is free; a call that *changes*
  its storage is a **transaction** (costs a small fee, and is recorded permanently).

Picture a **vending machine welded into a public square**: no shopkeeper, no back door. People
walk up and use it, it follows its fixed rules mechanically, and both the rules and the
contents are out in the open and tamper-proof. That is a smart contract.

## 2. The problem this particular contract solves

Ada's AI agent wants to buy 50 Mbps from Bell's AI agent. They are strangers — no shared
account, no prior trust. Ada pays… and gets **what**, exactly? A receipt emailed around could
be copied or forged. What she actually needs is a **thing she owns that the network itself
will check** — a ticket that

1. states **exactly what she is owed** (50 Mbps, this path, 14:00–16:00), and
2. **provably belongs to her**, recorded somewhere **no one can secretly edit** — not even
   Bell, who issued it.

Without such a place, every guarantee unravels: Bell could quietly change the terms, or claim
Ada never paid. `A2ASettlement` *is* that place.

## 3. The idea: a public registry of tickets

Think of a **land registry** — the official book that records, for each plot, its boundaries
and its current owner. You don't trust a seller's word that they own a house; you trust the
registry. `A2ASettlement` is a land registry for *service tickets* (we call each ticket an
**entitlement**). Its entire job is to hold, tamper-proof and public, rows like:

> **ticket #7** — issued by Bell — grants *bandwidth, 50 Mbps, path #7, 14:00→16:00* —
> owner **Ada** — revoked: no

## 4. What's inside the contract, line by line

The contract is declared at [`Settlement.sol:17`](../contracts/src/Settlement.sol#L17):

```solidity
contract A2ASettlement is ERC721 {
```

That little **`is ERC721`** is doing heavy lifting — we come back to it in §5. Inside are
three things, each answering one need.

**(a) The shape of a ticket — a `struct`** ([`:18–27`](../contracts/src/Settlement.sol#L18-L27)).
A *struct* is just "a named bundle of labelled fields", like a paper form with blanks. Ours,
`Entitlement`, has the eight things a ticket must say. Glossing the field types: `address` =
an account on the chain (Bell, Ada); `uint8`/`uint64` = whole numbers (8-bit, 64-bit);
`bytes32` = a 32-byte value (here used as an id or a fingerprint); `bool` = true/false.

```solidity
struct Entitlement {
    address issuer;      // who issued it      -> Bell
    uint8   serviceType; // 0 = bandwidth      -> bandwidth
    bytes32 resourceId;  // which path         -> #7
    bytes   params;      // the fine print     -> encodes "50 Mbps, class 1"
    uint64  startTime;   // valid from         -> 14:00
    uint64  endTime;     // valid until        -> 16:00
    bool    revoked;     // cancelled?         -> no
    bytes32 termsHash;   // fingerprint of the full off-chain SLA
}
```

Why keep this **on the chain** (in storage) rather than on Bell's website? Because a ticket
whose fine print can 404 or be edited overnight is useless to the gatekeeper who must enforce
it. Terms and ownership must share one tamper-proof home.

**(b) The filing cabinet — a `mapping`** ([`:32`](../contracts/src/Settlement.sol#L32)).

```solidity
mapping(uint256 => Entitlement) public entitlements;
```

A *mapping* is a lookup table: hand it a ticket number, get back that ticket's `Entitlement`.
So `entitlements[7]` *is* Ada's stored ticket. `public` means Solidity auto-writes a read
function so anyone can look up any ticket.

**(c) The ticket-printer — `_issue`** ([`:43–67`](../contracts/src/Settlement.sol#L43-L67)).
This *function* creates a new ticket. It does two writes (see the diagram in §6): fills a row
of the cabinet with the eight terms, and stamps the first owner. Two details to interrogate:

- `id = ++_lastId;` ([`:53`](../contracts/src/Settlement.sol#L53)) — ids count up from 1, so
  the very first ticket ever issued is #1. The story's "#7" just means *the seventh ticket
  Bell sold* (six came before Ada's).
- The word **`internal`** ([`:52`](../contracts/src/Settlement.sol#L52)) means *nothing
  outside the contract can call this*. Why deliberately cripple our own mint function? Because
  if anyone could call it, anyone could **print themselves a free 50 Mbps ticket**. Locking it
  guarantees the *only* path to a new ticket is the paid purchase function `fulfill` (built
  next milestone, M1.3). **The lock is the security**, and it has a name: invariant I1, "only
  `fulfill` mints."

## 5. The half you can't see: `is ERC721` (and what ERC-721 really is)

The struct stores a ticket's *terms*. But who **owns** ticket #7? Nothing above answers that —
because that half comes from **ERC-721**.

> **ERC-721 is the Ethereum standard for "a registry of unique, individually-owned items."**
> It is a shared, audited rulebook (we borrow OpenZeppelin's ready-made version). It is *not*
> about signing or identity — that confusion is common. Signing is how you authorise *any*
> action with your secret key, and it lives elsewhere (the `chainmcp` package, later).
> ERC-721 is purely an **ownership ledger**.

By writing `contract A2ASettlement is ERC721`, our contract **inherits** (receives for free,
without writing it) ERC-721's whole ownership system:

- `ownerOf(7)` → returns Ada's address. *"Who holds ticket #7?"*
- `transferFrom(Ada, Carol, 7)` → moves ticket #7 to Carol.
- the careful bookkeeping that keeps those safe.

We wrote **none** of that. That is the point: ownership logic is subtle and a bug there means
stolen tickets, so we stand on the audited standard and add only what is *ours* — the terms.

## 6. The two ledgers (why `_issue` writes in two places)

```mermaid
flowchart LR
    call["_issue(to=Ada, issuer=Bell, … )"]
    call -->|writes the 8 terms| terms["entitlements[7]  (our struct)\nBell · 50 Mbps · #7 · 14:00–16:00"]
    call -->|stamps first owner| owner["ERC-721 ledger\nownerOf(7) = Ada"]
```

Two separate records for ticket #7: **terms** in *our* mapping, **owner** in the *inherited*
ERC-721 ledger. Keeping them separate is what lets ownership move while terms stay frozen —
the next section.

## 7. The main tradeoff, and the classic beginner mistake

**Tradeoff.** Inheriting ERC-721 also inherits its assumption that tickets are freely
**transferable** — Ada *can* resell #7 to Carol. Some designs want non-transferable
("soulbound") tickets; we accept transferability (story ch. 8 even uses it). And writing to
on-chain storage costs *gas* (a fee) — but that fee buys the tamper-proofness, which is the
product.

**Common mistake.** Believing the *terms* travel with the *owner* — that selling the ticket
could change what it grants, or that the owner is stored inside the struct. It isn't: owner
lives in the ERC-721 ledger, terms live in the struct, and they are independent. Resell #7 and
the owner flips to Carol while *every term stays identical*. That exact property is invariant
**I6**, pinned by [`test_I6_termsSurviveTransfer`](../contracts/test/Settlement.t.sol).

## 8. The purchase (M1.3): how a signed promise becomes a ticket

Everything so far explained the *registry*. But how does a ticket get **sold**? Ada and
Bell are strangers on a network — Bell won't ship first, Ada won't pay first. The answer is
the vending machine move (story ch. 4): make payment and delivery **one indivisible step**,
so neither party can be left holding nothing.

**Step 1 — Bell signs an offer, off-chain.** An *offer* is twelve fields of data (who
sells, to whom, what service, which path, the window, which token, what price, a quote
deadline `validUntil`, a serial number `salt`, a fingerprint of the fine print). Bell runs
it through **EIP-712** — the Ethereum standard for signing *structured* data — and produces
a 65-byte **signature** with his secret key. Two things make this more than a scribble:

- The hash Bell signs includes a **domain**: *("A2AProvisioning", version "0", chain 31337,
  this contract's address)*. The same offer signed for a different chain or a different
  contract hashes differently — the signature only works in its home. That is anti-replay
  armor you get for free.
- From (hash, signature) anyone can *recover the signer's address* — a piece of EVM math
  called `ecrecover`. No account system, no password: the math is the authentication.

Note what did **not** happen: no transaction, no fee, the chain is unaware. An unsigned
offer is a rumor; a signed one is a redeemable promise sitting in a JSON file.

**Step 2 — Ada redeems it, on-chain.** Ada first `approve`s the settlement contract to
pull 10 TOK from her (ERC-20 payment is *pull*-based: you grant an **allowance**, the
contract collects). Then she calls the one public door:

```solidity
fulfill(offer, signature)   // Settlement.sol — the cashier
```

which runs a fixed pipeline — the same order, every time, for everyone:

1. **Is the quote still fresh?** `block.timestamp > validUntil` → refuse (`OfferExpired`).
2. **Is Ada the intended buyer?** If the offer names a consumer and it isn't the caller →
   refuse (`WrongConsumer`). (`0x0` = open offer, first come first served.)
3. **Was this promise already redeemed?** A ledger *in the contract's own storage* —
   `consumed[digest]` — remembers every punched stub. Already true → refuse
   (`OfferAlreadyUsed`). This is invariant **I2**: one promise, one redemption, enforced
   where every future buyer can see it, not in Bell's private database.
4. **Did Bell really sign these exact bytes?** Recover the signer from the signature; not
   `offer.provider` → refuse (`BadSignature`). Change *any* field — price, megabits,
   window — and recovery yields a stranger. Tampering is not "caught", it is
   *mathematically impossible to miss*.
5. **All checks pass:** punch the stub, pull 10 TOK from Ada to Bell, and `_issue` the
   ticket (yes — the same `internal` printer from §4(c); `fulfill` is its only production
   caller, which completes invariant **I1**). Two events announce it: `OfferConsumed`,
   `EntitlementMinted`.

**The magic is what happens on failure.** If *anything* reverts — say Ada never approved
the 10 TOK — the EVM rolls back **every** storage write of the transaction, including the
stub punched in step 5 before the payment ran. No ticket, no payment, salt still fresh, as
if nothing happened. That all-or-nothing is invariant **I3**, and it is *why* payment and
mint must live in one transaction rather than two cooperating ones.

**One deliberate non-check:** `fulfill` never looks at `startTime`/`endTime`. Buying at
13:45 for the 14:00 window is normal commerce; deciding whether the window is *currently
usable* is the controller's job at activation time (M4), against chain time.

**Where's the money itself?** A second, tiny contract: [`MockTOK`](../contracts/src/MockTOK.sol)
— a standard ERC-20 token (the fungible cousin of ERC-721: interchangeable units, balances
instead of unique ids) with an open `faucet` because it is stage money for the lab. The
settlement never holds TOK; it moves it straight buyer → provider.

## 9. How a ticket dies (M1.4): two opposite deaths, zero deletions

**Expiry is passive.** At 16:00 the chain does *nothing* — no timer, no callback, no flag.
"Expired" is a judgment any reader makes by comparing the stored `endTime` with chain
time. (So who turns off Ada's bandwidth? The controller, on its own clock — M4.5. The
chain only holds the facts.)

**Revocation is active.** Bell — and only Bell, the *issuer* (I4; Ada the owner gets
`NotIssuer`) — sends `revoke(7)`: one bit flips in storage and a `Revoked(7)` event fires.
That event is the controller's wake-up call to tear the session down mid-window.

**Neither death deletes anything** (I5, I8): the token keeps its owner, every term stays
readable, and the fine print (`tokenURI` — a self-contained `data:` JSON rendered from
storage on each call, I7) simply reports `"revoked": true`. A dead ticket is evidence,
not garbage.

## 10. See it — or break it — yourself

- **See it (storage + ownership):** [`contracts/EXPLORE-settlement.md`](../contracts/EXPLORE-settlement.md) —
  create ticket #7, read its terms off the chain, transfer it, watch the owner flip while
  the terms don't.
- **See it (the purchase):** [`contracts/EXPLORE-fulfill.md`](../contracts/EXPLORE-fulfill.md) —
  *be* Bell and Ada: sign a real offer with `cast`, redeem it, then replay it, underfund it,
  tamper with it, and let it expire — four refusals, each with its named error.
- **See it (the deaths):** [`contracts/EXPLORE-revoke.md`](../contracts/EXPLORE-revoke.md) —
  decode the on-chain fine print, watch expiry do nothing, pull the kill switch as Bell
  (and fail to as Ada).
- **Break it:** in [`fulfill`](../contracts/src/Settlement.sol), swap the two lines
  `consumed[digest] = true;` and the `safeTransferFrom(...)` call, then run `forge test`.
  Everything stays green — the EVM's rollback makes the order irrelevant for I3 — but now
  read the comment above those lines and `test_revertOrder_usedSaltWinsOverBadSignature`
  to see the *other* reason the punch comes first (a reentrant token trying the same offer
  twice mid-flight). Then revert.

---

**Check questions:** (1) When ticket #7 is stored, two different parts of the contract hold
two different facts — "the terms are 50 Mbps, 14:00–16:00" and "Ada is the owner." Which
part holds which, and why is it *useful* that they live separately? (2) Walk the six
effects of a successful `fulfill` (stub punched, TOK moved, ticket minted, owner stamped,
two events) and say what happens to each one if the payment pull reverts — and *why* that
answer needs no code at all.
