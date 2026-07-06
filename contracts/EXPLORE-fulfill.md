# Exploring M1.3 — buy ticket #7 by hand: sign, redeem, and try to cheat

In M1.2 the contract could *hold* a ticket but not *sell* one — the only mint path was a
test harness. M1.3 opens the production contract's one real door, `fulfill`. This lab walks
the whole chapter-4 purchase **by hand, from two keyboards**: you are Bell composing and
signing an offer *off-chain*, then Ada redeeming it *on-chain* — money and ticket in one
transaction. Then you try to cheat four different ways (replay, no funds, tampering, stale
quote) and watch the contract refuse each one, with the exact same error names the Python
skeleton's `FakeChain` raises. Every output below is from a real run.

> **Audience:** finished [`EXPLORE-settlement.md`](EXPLORE-settlement.md). Code:
> [`src/Settlement.sol`](src/Settlement.sol) (`fulfill`, `hashOffer`),
> [`src/MockTOK.sol`](src/MockTOK.sol), [`test/Fulfill.t.sol`](test/Fulfill.t.sol).
> Concepts: [`docs/04-contract-spec.md`](../docs/04-contract-spec.md) §3 (I2, I3), story ch. 4.

## The one idea: a signature turns a JSON blob into a promise

Bell's quote is just twelve fields of data — worthless until Bell signs it. **EIP-712** is
the Ethereum standard for signing *structured* data: instead of signing an opaque byte
string, Bell signs a hash built from (a) his offer's fields, each in a declared order and
type, and (b) a **domain** — the tuple *(name "A2AProvisioning", version "0", chainId
31337, the settlement contract's address)*. The domain is anti-replay armor: the same
twelve fields signed for another chain, or another contract, hash differently, so the
signature is dead outside its home. The contract can then `ecrecover` the signer's address
from (hash, signature) and check it equals `offer.provider`. No account, no session, no
provider database — the math *is* the authentication.

One EIP-712 rule worth meeting now, because it bites in M1.5: dynamic fields (our `bytes
params`) enter the struct hash as their own `keccak256`, never as raw bytes.

## Setup: a chain frozen at story time

The offer's fixture times live in September 2025 (`validUntil` = 14:20 story time). Your
wall clock is past that — but **your wall clock does not matter and never will** (ADR-004:
chain time is the only clock). Start the chain at 13:55, five minutes before Ada's window:

```sh
cd contracts
anvil --timestamp 1757944500          # terminal 1: chain time = 13:55 story time
```

```sh
# terminal 2 — the cast of characters (same keys as EXPLORE-settlement.md)
RPC=http://127.0.0.1:8545
ADA_KEY=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80    # anvil #0
BELL_KEY=0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d   # anvil #1
CAROL_KEY=0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a  # anvil #2
ADA=0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266
BELL=0x70997970C51812dc3A010C7d01b50e0d17dc79C8
CAROL=0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC
```

Deploy — **MockTOK first**, so it lands at the fixture address (`fixtures.MOCK_TOK` says
"anvil deploy[0]"; a fresh chain's deploy addresses depend only on deployer + nonce):

```sh
forge create src/MockTOK.sol:MockTOK --rpc-url $RPC --private-key $ADA_KEY --broadcast --json | jq -r .deployedTo
# -> 0x5FbDB2315678afecb367f032d93F642f64180aa3        == fixtures.MOCK_TOK ✓
forge create src/Settlement.sol:A2ASettlement --rpc-url $RPC --private-key $ADA_KEY --broadcast --json | jq -r .deployedTo
# -> 0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512
TOK=0x5FbDB2315678afecb367f032d93F642f64180aa3
SETTLEMENT=0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512
```

Note what we deployed: `A2ASettlement` itself, **no harness**. Last lab needed
`SettlementHarness` to smuggle tickets in; today the front door exists.

Two signatures you'll reuse all lab (the 12-field Offer tuple, spelled once):

```sh
FULFILL_SIG="fulfill((address,address,uint8,bytes32,bytes,uint64,uint64,address,uint256,uint64,bytes32,bytes32),bytes)"
HASH_SIG="hashOffer((address,address,uint8,bytes32,bytes,uint64,uint64,address,uint256,uint64,bytes32,bytes32))(bytes32)"
```

And lab money — 100 TOK to Ada from the open faucet:

```sh
cast send $TOK "faucet(address,uint256)" $ADA 100000000000000000000 --rpc-url $RPC --private-key $ADA_KEY
cast call $TOK "balanceOf(address)(uint256)" $ADA --rpc-url $RPC
# -> 100000000000000000000 [1e20]
```

## 1. Be Bell: compose and sign the offer (no chain involved)

Bell's offer is a **typed-data document** — the same twelve fields as `docs/03 §1.4`,
camelCase because this JSON *is* what gets hashed and verified. Save as `/tmp/offer-7.json`:

```json
{
  "types": {
    "EIP712Domain": [
      {"name": "name", "type": "string"},
      {"name": "version", "type": "string"},
      {"name": "chainId", "type": "uint256"},
      {"name": "verifyingContract", "type": "address"}
    ],
    "Offer": [
      {"name": "provider", "type": "address"},
      {"name": "consumer", "type": "address"},
      {"name": "serviceType", "type": "uint8"},
      {"name": "resourceId", "type": "bytes32"},
      {"name": "params", "type": "bytes"},
      {"name": "startTime", "type": "uint64"},
      {"name": "endTime", "type": "uint64"},
      {"name": "paymentToken", "type": "address"},
      {"name": "price", "type": "uint256"},
      {"name": "validUntil", "type": "uint64"},
      {"name": "salt", "type": "bytes32"},
      {"name": "termsHash", "type": "bytes32"}
    ]
  },
  "primaryType": "Offer",
  "domain": {
    "name": "A2AProvisioning",
    "version": "0",
    "chainId": 31337,
    "verifyingContract": "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512"
  },
  "message": {
    "provider": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
    "consumer": "0x0000000000000000000000000000000000000000",
    "serviceType": 0,
    "resourceId": "0x0000000000000000000000000000000000000000000000000000000000000007",
    "params": "0x0000000000000000000000000000000000000000000000000000000002faf0800000000000000000000000000000000000000000000000000000000000000001",
    "startTime": 1757944800,
    "endTime": 1757952000,
    "paymentToken": "0x5FbDB2315678afecb367f032d93F642f64180aa3",
    "price": "10000000000000000000",
    "validUntil": 1757946000,
    "salt": "0x0000000000000000000000000000000000000000000000000000000000005a17",
    "termsHash": "0x2222222222222222222222222222222222222222222222222222222222222222"
  }
}
```

Read the `message` aloud in story terms: *Bell (provider), open to anyone (consumer 0x0),
bandwidth (0), path #7, 50 Mbps class 1 (the `params` blob), window 14:00→16:00, paid in
TOK, price 10 TOK, quote valid until 14:20, stub serial 0x5a17, SLA fingerprint 0x22…*

Now sign it. **This happens entirely off-chain** — no transaction, no gas, the chain has no
idea Bell promised anything:

```sh
SIG=$(cast wallet sign --private-key $BELL_KEY --data --from-file /tmp/offer-7.json)
echo $SIG
# 0x892842e5b351d82e38b3911e2977ed09950abf1d692c9c57135b7d245219cfb7
#   6bc01360fc1917b40c6cf82170d94844a940d328d5eb089c059113ad3fb96986 1b     (65 bytes: r‖s‖v)

cast wallet verify --data --from-file /tmp/offer-7.json $SIG --address $BELL
# Validation succeeded. Address 0x70997970C51812dc3A010C7d01b50e0d17dc79C8 signed this message.
```

## 2. Trust, then verify: recompute both hashes yourself

Don't take the signing black box on faith. The type string's keccak must equal the
contract's constant, and cast's typed-data digest must equal the contract's `hashOffer` —
if either differs by one byte, every signature is garbage (this exact comparison, done
Python-vs-Solidity, is M1.5's centerpiece test):

```sh
cast keccak "Offer(address provider,address consumer,uint8 serviceType,bytes32 resourceId,bytes params,uint64 startTime,uint64 endTime,address paymentToken,uint256 price,uint64 validUntil,bytes32 salt,bytes32 termsHash)"
# 0x14da67f04d1d4e3c5800536c542a24924372ff20a8872c71ad7d89086bd71e6d
cast call $SETTLEMENT "OFFER_TYPEHASH()(bytes32)" --rpc-url $RPC
# 0x14da67f04d1d4e3c5800536c542a24924372ff20a8872c71ad7d89086bd71e6d          ← identical

PARAMS=0x0000000000000000000000000000000000000000000000000000000002faf0800000000000000000000000000000000000000000000000000000000000000001
OFFER="(0x70997970C51812dc3A010C7d01b50e0d17dc79C8,0x0000000000000000000000000000000000000000,0,0x0000000000000000000000000000000000000000000000000000000000000007,$PARAMS,1757944800,1757952000,$TOK,10000000000000000000,1757946000,0x0000000000000000000000000000000000000000000000000000000000005a17,0x2222222222222222222222222222222222222222222222222222222222222222)"
cast call $SETTLEMENT "$HASH_SIG" "$OFFER" --rpc-url $RPC
# 0xbc4955e34d4f9670e5fe370dab1be118b8bba1ce7f4b643622d902945cf3d9a6
DIGEST=0xbc4955e34d4f9670e5fe370dab1be118b8bba1ce7f4b643622d902945cf3d9a6
```

That 32-byte digest is *the thing Bell signed*. Everything else is plumbing around it.

## 3. Be Ada: redeem — money and ticket in the same breath

Two steps, because ERC-20 payment works by *pull*: Ada first grants the settlement contract
an **allowance** (permission to take exactly 10 TOK from her), then calls `fulfill`, during
which the contract pulls the payment and mints the ticket:

```sh
cast send $TOK "approve(address,uint256)" $SETTLEMENT 10000000000000000000 --rpc-url $RPC --private-key $ADA_KEY
cast send $SETTLEMENT "$FULFILL_SIG" "$OFFER" $SIG --rpc-url $RPC --private-key $ADA_KEY
# status 0x1 — one transaction, four events (see §4)
```

The world after, in four reads:

```sh
cast call $SETTLEMENT "ownerOf(uint256)(address)" 1 --rpc-url $RPC
# 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266                    Ada owns ticket #1
cast call $TOK "balanceOf(address)(uint256)" $ADA --rpc-url $RPC
# 90000000000000000000 [9e19]                                   Ada paid 10 …
cast call $TOK "balanceOf(address)(uint256)" $BELL --rpc-url $RPC
# 10000000000000000000 [1e19]                                   … Bell received 10
cast call $SETTLEMENT "consumed(bytes32)(bool)" $DIGEST --rpc-url $RPC
# true                                                          the stub is punched
```

Bell never touched the chain — he signed a JSON file. Ada's one transaction did everything:
verified his signature, moved her 10 TOK to him, minted her the ticket, punched the salt.

## 4. The receipts: four events, one gotcha

```sh
cast receipt <ADA_FULFILL_TX> --json --rpc-url $RPC | jq -r '.logs[].topics[0]'
# 0xddf252ad…523b3ef     Transfer          — the 10 TOK,  ERC-20  (on MockTOK)
# 0xddf252ad…523b3ef     Transfer          — ticket #1,   ERC-721 (on A2ASettlement)
# 0x82b63048…0739b80     OfferConsumed(bytes32)
# 0x616b683a…13d4d29a    EntitlementMinted(id, issuer, serviceType, consumer)
```

Gotcha worth savoring: **ERC-20 and ERC-721 `Transfer` events share the same topic0**
(both hash `"Transfer(address,address,uint256)"`) — you tell money from ticket by the
*emitting address*. The `EntitlementMinted` log is what the dashboard (M6.4) will narrate,
and `Revoked` (M1.4) is what the controller will subscribe to.

## 5. Cheat #1 — replay: run the exact same command again

The offer is signed, the signature is valid, Ada still has 90 TOK. Redeem it twice?

```sh
cast send $SETTLEMENT "$FULFILL_SIG" "$OFFER" $SIG --rpc-url $RPC --private-key $ADA_KEY
# Error: execution reverted: custom error 0xa762b3be: OfferAlreadyUsed
cast sig "OfferAlreadyUsed()"
# 0xa762b3be                                 ← that's how you decode an unnamed selector
```

Invariant **I2**. The `consumed[digest] = true` you read in §3 *is* the vending machine
remembering the stub — a ledger on the chain itself, not in Bell's database, so *every*
future buyer sees the same punched stub (`test_I2_replayByAnotherBuyerReverts`).

## 6. Cheat #2 — no funds: watch the whole world roll back (I3)

Bell signs a **second** offer (fresh salt `0x5a18` = a genuinely new promise needing a new
signature). Carol grabs it, has 100 TOK — but *forgets to approve*:

```sh
jq '.message.salt = "0x0000000000000000000000000000000000000000000000000000000000005a18"' /tmp/offer-7.json > /tmp/offer-8.json
SIG2=$(cast wallet sign --private-key $BELL_KEY --data --from-file /tmp/offer-8.json)
OFFER2=…same tuple, salt 0x…5a18…                 # rebuild as in §2
DIGEST2=$(cast call $SETTLEMENT "$HASH_SIG" "$OFFER2" --rpc-url $RPC)
cast send $TOK "faucet(address,uint256)" $CAROL 100000000000000000000 --rpc-url $RPC --private-key $ADA_KEY

cast send $SETTLEMENT "$FULFILL_SIG" "$OFFER2" $SIG2 --rpc-url $RPC --private-key $CAROL_KEY
# Error: execution reverted: ERC20InsufficientAllowance(0xe7f1…0512, 0, 10000000000000000000)
```

The revert happened at step "funds" — *after* the contract had already marked the salt
consumed in storage. Did that earlier write survive?

```sh
cast call $SETTLEMENT "consumed(bytes32)(bool)" $DIGEST2 --rpc-url $RPC
# false                                        salt unpunched
cast call $SETTLEMENT "ownerOf(uint256)(address)" 2 --rpc-url $RPC
# Error: custom error 0x7e273289 …0002         ticket #2 never existed
cast call $TOK "balanceOf(address)(uint256)" $CAROL --rpc-url $RPC
# 100000000000000000000 [1e20]                 Carol still rich
```

**Nothing survived.** A revert rolls back *every* storage write of the transaction —
that's invariant **I3**, and it's the EVM's gift: the Python `FakeChain` had to earn
atomicity by carefully ordering checks before mutations; the contract gets it by
physics. Same offer, same signature, after `approve`: succeeds, Carol owns ticket #2.

```sh
cast send $TOK "approve(address,uint256)" $SETTLEMENT 10000000000000000000 --rpc-url $RPC --private-key $CAROL_KEY
cast send $SETTLEMENT "$FULFILL_SIG" "$OFFER2" $SIG2 --rpc-url $RPC --private-key $CAROL_KEY
cast call $SETTLEMENT "ownerOf(uint256)(address)" 2 --rpc-url $RPC
# 0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC   (Carol)
```

## 7. Cheat #3 — tamper: a one-field discount

Bell signs a third offer at 10 TOK (salt `0x5a19`). Submit it with `price` quietly changed
to 1 TOK — every other byte identical, signature untouched:

```sh
# tuple identical except price: 1000000000000000000 (1 TOK instead of 10)
cast send $SETTLEMENT "$FULFILL_SIG" "$TAMPERED" $SIG3 --rpc-url $RPC --private-key $ADA_KEY
# Error: execution reverted: custom error 0x5cd5d233: BadSignature
```

Change any of the twelve fields and the struct hash changes, so recovery yields *some
other address* than Bell — `BadSignature`. This is the property that later makes
**offers safe to relay over the untrusted A2A wire** (M5.5 tampers one field in transit
and watches this exact error catch it end-to-end).

## 8. Cheat #4 — the stale quote: time travel past validUntil

Bell signs a fresh, perfectly valid offer (salt `0x5a1a`). Then the chain's clock — the
only clock that counts — jumps a day:

```sh
cast rpc evm_increaseTime 86400 --rpc-url $RPC && cast rpc evm_mine --rpc-url $RPC
cast block latest --rpc-url $RPC | grep timestamp
# timestamp  1758031021 (Tue, 16 Sep 2025 13:57:01 +0000)

cast send $SETTLEMENT "$FULFILL_SIG" "$OFFER4" $SIG4 --rpc-url $RPC --private-key $ADA_KEY
# Error: execution reverted: custom error 0x9cb13087: OfferExpired
```

`validUntil` is the *quote's* shelf life (14:20), not the service window — Bell won't
honor Tuesday's price forever. Note what `fulfill` deliberately does **not** check:
`startTime`/`endTime`. Buying at 13:45 for the 14:00 window is normal; *using* the window
is the controller's decision at activation time (M4), against chain time (ADR-004).

## What you learned (and where it goes)

| You did | The concept | Next |
|---|---|---|
| signed JSON with `cast wallet sign --data` | EIP-712: structured signing under a domain | Python signs the same bytes (M1.5) |
| `OFFER_TYPEHASH` == your own `cast keccak` | the type string is public, recomputable truth | cross-stack signature test (M1.5) |
| approve → fulfill | ERC-20 pull payment + atomic settlement | agents do this via MCP tools (M5.4) |
| replay → `OfferAlreadyUsed` | I2: on-chain single-use ledger, keyed by digest | provider needs no database |
| failed tx changed *nothing* | I3: revert rolls back all storage writes | why payment+mint share one tx |
| tampered field → `BadSignature` | integrity travels with the data | A2A wire tamper demo (M5.5) |
| `evm_increaseTime` → `OfferExpired` | chain time is the only clock (ADR-004) | expiry/`vm.warp` tests (M1.4) |

## Experiments to try

- **The M1.5 bug, today:** change `"version": "0"` to `"1"` in the domain of a fresh
  offer, re-sign, submit — `BadSignature`, with everything else perfect. Domain mismatch
  is *the* classic cross-stack failure; you now know its exact symptom.
- Make a **consumer-bound** offer (`consumer` = Ada) and let Carol try to redeem it
  (predict the error before you run it — check the fake's order: which check fires first
  if it's *also* expired?).
- Same salt `0x5a17`, but price 20 TOK, freshly signed by Bell — does it revert as
  already-used, or mint? Explain why the ledger keyed by *digest* makes this the honest
  answer, and why a provider must still randomize salts.
- `cast call $SETTLEMENT "fulfill(...)" …` (a *call*, not a send) — it returns the
  would-be entitlement id without spending anything. Free dry runs, courtesy of
  call-vs-transaction (EXPLORE.md).
