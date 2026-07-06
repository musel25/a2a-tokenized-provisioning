# Exploring M1.4 — the ticket ages and dies (but never disappears)

Ticket #7 was bought in the last lab. This one is about the rest of its life: reading its
**fine print straight off the chain** (`tokenURI`), watching **expiry do exactly nothing**
(the deepest idea in this milestone), and pulling the **kill switch** (`revoke`) — who may,
who may not, and what actually changes. Along the way you use the *real deploy script* for
the first time: one command that stands up the whole settlement layer and writes the
address file every Python package will read from M1.5 on. All outputs are from a real run.

> **Audience:** finished [`EXPLORE-fulfill.md`](EXPLORE-fulfill.md). Code:
> [`src/Settlement.sol`](src/Settlement.sol) (`revoke`, `tokenURI`),
> [`script/Deploy.s.sol`](script/Deploy.s.sol), [`test/Revoke.t.sol`](test/Revoke.t.sol).
> Concepts: [`docs/04-contract-spec.md`](../docs/04-contract-spec.md) §3 (I4, I5, I7, I8),
> story ch. 8.

## The two ways a ticket dies — and why they're opposites

- **Expiry is passive.** At 16:00 the chain does *nothing*. No function runs, no flag
  flips, no event fires. "Expired" is a judgment a reader makes by comparing the stored
  window against chain time — it is not a state the ticket enters. (Whoever must *act* on
  expiry — tearing down the bandwidth — is the controller, on its own timer: M4.5.)
- **Revocation is active.** Bell decides mid-window to kill the ticket, sends a
  transaction, one bit flips in storage, and a `Revoked` event fires for anyone
  listening. That event is exactly what the controller will subscribe to.

Both leave the ticket fully readable forever (I8): a dead ticket is *evidence*, and the
controller must be able to say "denied *because* revoked/expired" — impossible if death
deleted the record.

## Setup: one command instead of two `forge create`s

```sh
anvil --timestamp 1757944500        # terminal 1: story time 13:55, as always
```

```sh
# terminal 2, from the REPO ROOT this time:
just deploy-local
```
```
Script ran successfully.

## Setting up 1 EVM.
==========================
Chain 31337
…2 transactions: MockTOK, then A2ASettlement…
ONCHAIN EXECUTION COMPLETE & SUCCESSFUL.
--- contracts/deployments/anvil.json ---
{
  "A2ASettlement": "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512",
  "MockTOK": "0x5FbDB2315678afecb367f032d93F642f64180aa3",
  "chainId": 31337,
  "v": 0
}
```

That JSON file is the deploy's *artifact* — the "where to find the chain" map
(docs/03 §2.4). In M1.5 the Python `ChainClient`'s first act will be reading it. Note
MockTOK deploys first, so it lands at the address `fixtures.MOCK_TOK` promised.

Now give yourself a live ticket to kill — the previous lab's purchase, compressed
(same env vars and `/tmp/offer-7.json` as [`EXPLORE-fulfill.md`](EXPLORE-fulfill.md)):

```sh
cast send $TOK "faucet(address,uint256)" $ADA 100000000000000000000 --rpc-url $RPC --private-key $ADA_KEY
SIG=$(cast wallet sign --private-key $BELL_KEY --data --from-file /tmp/offer-7.json)
cast send $TOK "approve(address,uint256)" $SETTLEMENT 10000000000000000000 --rpc-url $RPC --private-key $ADA_KEY
cast send $SETTLEMENT "$FULFILL_SIG" "$OFFER" $SIG --rpc-url $RPC --private-key $ADA_KEY
# ticket #1 → Ada
```

## 1. The fine print with no web server behind it (I7)

Most NFTs answer `tokenURI` with an `https://…` link — a promise that some server, run by
someone, will keep serving the metadata forever. Ours builds the JSON *from storage, on
every call*, and hands it back as a self-contained `data:` URI:

```sh
URI=$(cast call $SETTLEMENT "tokenURI(uint256)(string)" 1 --rpc-url $RPC)
echo $URI | head -c 90
# "data:application/json;base64,eyJuYW1lIjoiQTJBIEVudGl0bGVtZW50ICMxIiwiaXNzdWVyIjoiMHg3MDk5...

echo $URI | tr -d '"' | cut -d, -f2 | base64 -d | jq .
```
```json
{
  "name": "A2A Entitlement #1",
  "issuer": "0x70997970c51812dc3a010c7d01b50e0d17dc79c8",
  "serviceType": 0,
  "resourceId": "0x0000000000000000000000000000000000000000000000000000000000000007",
  "startTime": 1757944800,
  "endTime": 1757952000,
  "revoked": false,
  "termsHash": "0x2222222222222222222222222222222222222222222222222222222222222222"
}
```

Every value you see was read from the `Entitlement` struct at render time — nothing is
cached, nothing is hosted (I7: derived *purely* from storage;
`test_I7_tokenURIDerivesPurelyFromStorage` pins the exact bytes). `params` is deliberately
absent: an ABI blob isn't JSON-friendly, and decoders get it from `entitlements(1)`.

## 2. Watch expiry do nothing (I8)

The window ends at 16:00 (`endTime` 1757952000). Time-travel past it:

```sh
cast rpc evm_increaseTime 8000 --rpc-url $RPC && cast rpc evm_mine --rpc-url $RPC
cast block latest --rpc-url $RPC | grep timestamp
# timestamp   1757952584 (Mon, 15 Sep 2025 16:09:44 +0000)     ← past the window

cast call $SETTLEMENT "ownerOf(uint256)(address)" 1 --rpc-url $RPC
# 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266                    still Ada's

# and the fine print?
[ "$URI" = "$(cast call $SETTLEMENT "tokenURI(uint256)(string)" 1 --rpc-url $RPC)" ] \
  && echo "byte-identical"
# byte-identical
```

**The chain did nothing at 16:00.** No cron, no callback, no flag. The ticket is
"expired" only in the sense that any reader comparing `endTime` to chain time can now
judge it so. This is why the *controller* needs its own expiry watcher (M4.5) — nobody
else is going to act.

## 3. The kill switch — and who may not pull it (I4)

Ada *owns* the ticket. Can she revoke it?

```sh
cast send $SETTLEMENT "revoke(uint256)" 1 --rpc-url $RPC --private-key $ADA_KEY
# Error: execution reverted: custom error 0x54ec5063: NotIssuer
```

No — and think about why: revocation is the *issuer's* emergency brake on his own promise
(Bell terminating for abuse, story ch. 8). The owner "revoking" would just be… choosing
not to use her ticket. The switch belongs to the party *bound* by the promise, not its
beneficiary. (`test_I4_ownerCannotRevoke` — and note an unminted id fails the same way:
its issuer slot is `address(0)`, which no sender can be.)

Bell pulls it:

```sh
cast send $SETTLEMENT "revoke(uint256)" 1 --rpc-url $RPC --private-key $BELL_KEY --json | jq -r '.logs[0].topics'
# [
#   "0x61e27b0b…3135c760",     ← keccak("Revoked(uint256)")  — the controller's wake-up call
#   "0x0000…0001"              ← id 1, indexed
# ]
```

## 4. What death looks like: one bit (I5)

```sh
cast call $SETTLEMENT "tokenURI(uint256)(string)" 1 --rpc-url $RPC | tr -d '"' | cut -d, -f2 | base64 -d | jq '{name, revoked}'
# { "name": "A2A Entitlement #1", "revoked": true }         ← the fine print flipped live

cast call $SETTLEMENT "ownerOf(uint256)(address)" 1 --rpc-url $RPC
# 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266                 ← STILL Ada's token
```

Not burned, not deleted, terms untouched — `revoked: true` is the entire diff
(`test_I5_revokeDoesNotBurnOrRewriteTerms` asserts all eight fields). The ticket's history
remains public evidence of what was promised and what was withdrawn.

## What you learned (and where it goes)

| You did | The concept | Next |
|---|---|---|
| `just deploy-local` → anvil.json | the deploy artifact Python reads | ChainClient's first line (M1.5) |
| base64-decoded `tokenURI` | I7: fine print rendered from storage | dashboards read it (M6.4) |
| time-jumped past 16:00, nothing moved | expiry is passive (ADR-004) | controller's expiry timer (M4.5) |
| Ada's revoke → `NotIssuer` | I4: the brake belongs to the promiser | provider agent policy (M5.3) |
| Bell's revoke → `Revoked` event, one bit | I5: flag, never burn; I8: dead ≠ gone | the watcher + live teardown (M4.5) |

## Experiments to try

- Revoke ticket #1 **again** from Bell's key. Predict first: error or success? (Check
  `test_revokeTwiceIsIdempotent`, then the comment above `revoke` for the *why*.)
- Try to `fulfill` a fresh offer for a **revoked** resource — does anything in `fulfill`
  care about revocation? Should it? (Hint: what does the ticket represent, and who checks
  validity at *use* time?)
- Subscribe like the future controller will:
  `cast logs --address $SETTLEMENT "Revoked(uint256)" --from-block 0 --rpc-url $RPC` —
  then revoke another ticket and run it again. That polling loop *is* M4.5's watcher, in
  one command.
- Deploy on a **fresh** anvil twice in a row and diff the two `anvil.json`s — same
  addresses. Why? (deployer + nonce; the fixtures depend on it.)
