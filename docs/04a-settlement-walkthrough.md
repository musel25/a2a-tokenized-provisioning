# 04a — Settlement, for a complete beginner: what the contract *is* and why

> **The one-sentence answer:** `A2ASettlement` is a program that lives on a blockchain and
> acts as the **public, tamper-proof registry of service "tickets"** — for every ticket it
> records *what it grants* and *who owns it*, so a network gatekeeper can later trust the
> answer to "does Ada own a valid 50 Mbps ticket?"
>
> **Audience:** never written Solidity. Every term is glossed on first use. The runnable
> companion is [`contracts/EXPLORE-settlement.md`](../contracts/EXPLORE-settlement.md); the
> terse invariant list is [`docs/04-contract-spec.md`](04-contract-spec.md); the code is
> [`contracts/src/Settlement.sol`](../contracts/src/Settlement.sol) (68 lines).

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

## 8. See it — or break it — yourself

- **See it:** [`contracts/EXPLORE-settlement.md`](../contracts/EXPLORE-settlement.md) — start a
  local chain, create ticket #7, read its terms straight off the chain, transfer it, watch the
  owner flip while the terms don't.
- **Break it:** in [`_issue`](../contracts/src/Settlement.sol#L55), change `issuer: issuer` to
  `issuer: msg.sender`, then run `forge test`. Watch `test_issueStoresAllEightFieldsVerbatim`
  go red — proof the test really checks that *Bell* is recorded as the issuer. Then revert.

---

**Check question:** When ticket #7 is stored, two different parts of the contract hold two
different facts — "the terms are 50 Mbps, 14:00–16:00" and "Ada is the owner." Which part
holds which, and why is it *useful* that they live separately?
