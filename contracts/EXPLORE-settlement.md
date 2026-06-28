# Exploring M1.2 — the entitlement, on a real chain

A hands-on tour of `A2ASettlement`: deploy it to a local chain, **mint ticket #7 into
contract storage, read its terms straight back off the chain, and watch a resale move the
owner but not the terms** (invariant I6). Every command is real and every output below was
captured from an actual run.

> **Audience:** beginner to Solidity/EVM; finish [`EXPLORE.md`](EXPLORE.md) first (it teaches
> `forge`/`anvil`/`cast` and the call-vs-transaction idea). Code: [`src/Settlement.sol`](src/Settlement.sol),
> [`test/Settlement.t.sol`](test/Settlement.t.sol). Concepts: [`docs/04-contract-spec.md`](../docs/04-contract-spec.md)
> (the invariants), story ch. 2 (why a ticket).

## The one twist: there is no public "mint"

M1.2's whole point is invariant **I1** — *only `fulfill` mints* — and `fulfill` doesn't
exist yet (it lands at M1.3). The mint helper `_issue` is `internal`, so on the real
`A2ASettlement` **no transaction you can send will create a ticket.** That's the security
property, not a missing feature.

So to *see* a populated entitlement today, we deploy the **test harness**
(`SettlementHarness`), the same trick the tests use: a throwaway subclass that exposes
`_issue` as `exposed_issue`. On a real deployment you'd ship `A2ASettlement` and the only way
to fill it would be `fulfill`. The harness is a lab instrument, never production.

## Setup

```sh
cd contracts
anvil                       # terminal 1: local chain on :8545 (acct0 = Ada, acct1 = Bell)
```

```sh
# terminal 2
RPC=http://127.0.0.1:8545
KEY0=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80   # anvil acct0 = Ada
ADA=0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266
BELL=0x70997970C51812dc3A010C7d01b50e0d17dc79C8
CAROL=0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC
RID=0x0000000000000000000000000000000000000000000000000000000000000007    # ticket #7's resourceId
TH=0x2222222222222222222222222222222222222222222222222222222222222222     # placeholder termsHash
ETUP="(address,uint8,bytes32,bytes,uint64,uint64,bool,bytes32)"           # the Entitlement tuple

# the on-chain params blob = abi.encode(uint64 capacityBps, uint8 qosClass)
PARAMS=$(cast abi-encode "f(uint64,uint8)" 50000000 1)

forge create test/Settlement.t.sol:SettlementHarness \
  --rpc-url $RPC --private-key $KEY0 --broadcast --json | jq -r .deployedTo
# -> 0x5FbDB2315678afecb367f032d93F642f64180aa3
ADDR=0x5FbDB2315678afecb367f032d93F642f64180aa3
```

> 🔎 Same `0x5FbD…aa3` again — a fresh chain's first deploy is deterministic (deployer +
> nonce). `EXPLORE.md` saw it for the Counter; it's also `fixtures.MOCK_TOK`.

## 1. Before any mint: the existence gotcha

Read entitlement #7 before it exists. The struct mapping has **no "exists" bit**, so you get
an all-zero struct — *not* an error:

```sh
cast call $ADDR "entitlements(uint256)$ETUP" 7 --rpc-url $RPC
```
```
0x0000000000000000000000000000000000000000      # issuer
0                                               # serviceType
0x0000…0000                                     # resourceId
0x                                              # params (empty bytes)
0   0   false                                   # start, end, revoked
0x0000…0000                                     # termsHash
```

But `ownerOf` *does* revert — that is how you ask "does this ticket exist?":

```sh
cast call $ADDR "ownerOf(uint256)(address)" 7 --rpc-url $RPC
# Error: execution reverted: custom error 0x7e273289: …0007
```

`0x7e273289` is OZ's `ERC721NonexistentToken(uint256)` (verify: `cast sig
"ERC721NonexistentToken(uint256)"`), and the trailing `…0007` is the token id. **Lesson the
controller will depend on (M4): judge existence by `ownerOf`, never by the struct read.**

## 2. Mint the canonical ticket, read it back from storage

Mint #7's terms to Ada — issuer Bell, bandwidth, 50 Mbps, window 14:00–16:00. (First mint on
a fresh chain gets **id 1**; the story's "#7" is the 7th issue — see
`test_canonicalTicketIsTheSeventhIssue`.)

```sh
cast send $ADDR "exposed_issue(address,address,uint8,bytes32,bytes,uint64,uint64,bytes32)" \
  $ADA $BELL 0 $RID $PARAMS 1757944800 1757952000 $TH --rpc-url $RPC --private-key $KEY0
# status 0x1 (success), mined in block 2
```

Now read the terms **straight out of chain storage**:

```sh
cast call $ADDR "entitlements(uint256)$ETUP" 1 --rpc-url $RPC
```
```
0x70997970C51812dc3A010C7d01b50e0d17dc79C8                          # issuer  = Bell
0                                                                   # serviceType = bandwidth
0x0000000000000000000000000000000000000000000000000000000000000007 # resourceId = #7
0x…02faf080…0001                                                    # params (50e6, 1)
1757944800   1757952000   false                                     # 14:00, 16:00, not revoked
0x2222…2222                                                         # termsHash
cast call $ADDR "ownerOf(uint256)(address)" 1 --rpc-url $RPC
# -> 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266   (Ada)
```

The `params` field is opaque to the contract — a blob the controller decodes later
(docs/03 §4.2). Decode it yourself (no chain needed):

```sh
cast abi-decode "f()(uint64,uint8)" $PARAMS
# 50000000 [5e7]      <- capacityBps (50 Mbps)
# 1                   <- qosClass
```

## 3. I6 — a resale moves the owner, not the terms

Ada sells the NFT to Carol. ERC-721 transfers ownership; the entitlement's terms must stay
frozen (a ticket whose seat number changes hands is worthless):

```sh
cast send $ADDR "transferFrom(address,address,uint256)" $ADA $CAROL 1 \
  --rpc-url $RPC --private-key $KEY0          # sent by Ada, the owner
# status 0x1

cast call $ADDR "ownerOf(uint256)(address)" 1 --rpc-url $RPC
# -> 0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC   (Carol — ownership moved)

cast call $ADDR "entitlements(uint256)$ETUP" 1 --rpc-url $RPC
# -> issuer still Bell, resourceId still #7, params/window/termsHash all identical
```

Owner changed; **every term identical**. That is invariant I6 demonstrated on a live chain,
the same thing `test_I6_termsSurviveTransfer` asserts in-EVM.

## What you learned (and where it goes)

| You ran | The concept | Next |
|---|---|---|
| `ownerOf(7)` reverts vs `entitlements(7)`=zeros | existence ≠ a zero struct | controller existence checks (M4) |
| `exposed_issue` via the harness | minting is `internal` — I1, no public mint | real mint = `fulfill` (M1.3) |
| `entitlements(1)` returns the 8-tuple | terms live in chain storage, not a URL | Python `EntitlementView` reads this (M1.5) |
| transfer → owner moves, terms don't | invariant I6 | the ticket is load-bearing (ch. 3) |
| `cast abi-decode` the params | `serviceType`-tagged encoding | controller translators (M4.3) |

## Experiments to try

- Mint twice, then `ownerOf(2)` — predict the id before you read it.
- Try to find a public mint on the *real* contract: `cast interface $ADDR` then look — there
  is none. That absence is I1.
- Transfer #1 again from Carol's key (anvil acct2) — and from Ada's (now not the owner): one
  succeeds, one reverts. Why?
- `forge inspect src/Settlement.sol:A2ASettlement abi` — the ABI M1.5's Python will load.
