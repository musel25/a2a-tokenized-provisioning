# Exploring M1.1 — a hands-on Foundry lab

A guided, copy-paste tour of the `Counter` hello-world. By the end you'll have compiled
and tested a contract, run a local blockchain, deployed to it, and *felt* the single most
important distinction in this whole project: **a call vs a transaction**. The commands are
real and the outputs shown are captured from an actual run.

> **Audience:** beginner to Solidity/EVM. Jargon is glossed on first use. The conceptual
> companion (why any of this exists) is the M1.1 evidence file
> [`docs/evidence/M1.1.md`](../docs/evidence/M1.1.md); the code is `src/Counter.sol`,
> `test/Counter.t.sol`, `script/DeployCounter.s.sol`.

The three tools you'll use, all from Foundry:
- **`forge`** — compile, test, deploy (the build tool).
- **`anvil`** — a local throwaway blockchain on your laptop (the "flight simulator").
- **`cast`** — a CLI to poke a contract: read it, send transactions, read logs.

---

## 0. One-time setup

From the repo root, make sure Foundry is installed and the `forge-std` test library
(a git submodule) is present:

```sh
forge --version                       # e.g. forge Version: 1.5.1-stable
git submodule update --init --recursive   # fetches contracts/lib/forge-std
```

All commands below run **inside `contracts/`**:

```sh
cd contracts
```

---

## 1. Offline: build & test (no blockchain needed)

`forge test` spins up a tiny in-memory EVM, so you can test without any running chain.

```sh
forge build           # compile src/ + test/ with the pinned solc 0.8.30
forge test            # run every test/*.t.sol
forge test -vv        # -vv shows console logs; -vvvv shows full call traces
forge test --gas-report           # per-function gas table
forge test --match-test incrementEmits   # run one test by name substring
```

Real output of `forge test`:

```
Ran 3 tests for test/Counter.t.sol:CounterTest
[PASS] test_incrementAddsOne() (gas: 33228)
[PASS] test_incrementEmitsEvent() (gas: 34335)
[PASS] test_startsAtZero() (gas: 7870)
Suite result: ok. 3 passed; 0 failed; 0 skipped
```

**What to look at:** open [`test/Counter.t.sol`](test/Counter.t.sol). `setUp()` runs before
*each* test and gives every test a fresh `Counter` (no shared state between tests).
`test_incrementEmitsEvent` uses `vm.expectEmit(...)` — a Foundry **cheatcode** (test-only
superpower) that asserts "the next call must emit exactly this event." Break it on purpose:
change the contract to `emit Incremented(msg.sender, number + 1)` and re-run — that test
goes red, proving it really checks the event's data.

---

## 2. Online: run a local chain and talk to it

Now the fun part. Open **two terminals** (or background `anvil`).

### 2a. Start the chain

```sh
anvil
```

`anvil` prints 10 funded test accounts and their private keys, and listens on
`http://127.0.0.1:8545`. Account **#0** is `0xf39F…2266` (this is "Ada" in our fixtures!)
with the well-known dev key below.

> ⚠️ `0xac09…ff80` is **anvil's public, hard-coded dev key #0**. It's safe in the lab and in
> every Foundry tutorial — **never** use it on a real network.

In your second terminal, set two shell variables so the rest is copy-paste:

```sh
RPC=http://127.0.0.1:8545
KEY=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80   # anvil acct #0
```

### 2b. Deploy the Counter

```sh
forge script script/DeployCounter.s.sol --rpc-url $RPC --broadcast --private-key $KEY
```

`--broadcast` is the switch that turns the script's `vm.startBroadcast()` block into **real
transactions** sent to anvil (without it, the script only *simulates*). Real output ends with:

```
Script ran successfully.
ONCHAIN EXECUTION COMPLETE & SUCCESSFUL.
```

Grab the deployed address (it's in the broadcast log):

```sh
ADDR=$(jq -r '.transactions[0].contractAddress' broadcast/DeployCounter.s.sol/31337/run-latest.json)
echo $ADDR     # -> 0x5fbdb2315678afecb367f032d93f642f64180aa3
```

> 🔎 That address isn't random: on a fresh anvil, account #0's *first* deploy is always
> `0x5FbD…aa3` (an address derives deterministically from deployer + nonce). It's the same
> value `fixtures.MOCK_TOK` uses — addresses on a fresh chain are predictable.

### 2c. The lesson: a CALL vs a TRANSACTION

**Read** the number with a `cast call` — free, instant, needs no key, changes nothing:

```sh
cast call $ADDR "number()(uint256)" --rpc-url $RPC
# -> 0
```

Now **try to change it with a call** — and watch nothing happen:

```sh
cast call $ADDR "increment()" --rpc-url $RPC      # -> 0x   (a simulated result, discarded)
cast call $ADDR "number()(uint256)" --rpc-url $RPC
# -> 0    ← STILL ZERO. A call never persists. This is the "aha".
```

Now **send a transaction** — signed with a key, costs gas, mined into a block, permanent:

```sh
cast send $ADDR "increment()" --rpc-url $RPC --private-key $KEY
```

Real receipt (trimmed):

```
status               1 (success)
blockNumber          2
gasUsed              45187
transactionHash      0x5d3fbf03ff4a6c762730bb6badc43a0a332f56626934b9430d1acf23b75b9bc4
logs                 [{ ...Incremented... }]
```

Read again — now it stuck:

```sh
cast call $ADDR "number()(uint256)" --rpc-url $RPC
# -> 1
```

**That is the whole concept in your hands:** `cast call increment()` left `number` at 0;
`cast send increment()` made it 1. Reads are free simulations; only a *transaction* changes
the shared world (and only a transaction can emit an event or cost gas).

### 2d. The event in the logs

The `send` emitted `Incremented`. Read it back:

```sh
cast logs "Incremented(address,uint256)" --rpc-url $RPC --from-block 0
```

```
topics: [
    0x38ac789ed44572701765277c4d0970f2db1c1a571ed39e84358095ae4eaa5420   # topic0 = event signature hash
    0x000000000000000000000000f39fd6e51aad88f6f4ce6ab8827279cfffb92266   # topic1 = indexed `by` (acct #0)
]
data: 0x0000000000000000000000000000000000000000000000000000000000000001   # newNumber = 1
```

A **log** has up to 4 *topics* (indexed, searchable) plus *data* (the rest). Here `topic0` is
the event's identity, `topic1` is the `indexed` sender, and `data` holds `newNumber`. Verify
`topic0` yourself — it's just a hash of the signature:

```sh
cast sig-event "Incremented(address,uint256)"
# -> 0x38ac789ed44572701765277c4d0970f2db1c1a571ed39e84358095ae4eaa5420
```

This is exactly how the controller's revoke-watcher will work later: it subscribes to
`Revoked(uint256 indexed id)`, filters by the ticket id in a topic, and reacts off-chain the
instant the event appears — events are notifications **for the outside world** (no contract
can read them).

### 2e. Inspect the contract

```sh
forge inspect src/Counter.sol:Counter abi      # the JSON ABI (what M1.5's Python will read)
cast sig "increment()"                          # the 4-byte function selector -> 0xd09de08a
cast interface $ADDR --rpc-url $RPC             # reconstruct a Solidity interface (if verified)
```

### 2f. Stop the chain

`Ctrl-C` the `anvil` terminal (or `kill %1` if you backgrounded it). anvil is in-memory —
everything you did vanishes. Re-run from 2a for a clean slate.

---

## 3. What you learned (and where it goes)

| You ran | The concept | In this project (later) |
|---|---|---|
| `cast call number()` | a **call** — free, read-only, no key | the controller's `ownerOf(7)` / revoked / window reads |
| `cast send increment()` | a **transaction** — signed, gas, permanent | `fulfill()` (M1.3): the one write that swaps TOK for the ticket |
| `cast logs Incremented` | an **event** — outward notification | `Revoked(id)` the controller's watcher subscribes to (M1.4/M4.5) |
| pinned `solc`, submodule lib | reproducible builds | the Python signer must hash with the *same* compiler (M1.5) |

`Counter` is a throwaway; the real `A2ASettlement` (entitlements, EIP-712, atomic `fulfill`)
is M1.2–M1.4. But the toolchain and these three verbs are exactly what it's built on.

## 4. Experiments to try

- Send `increment()` twice, then `cast call number()` — predict before you read.
- `cast balance 0xf39F…2266 --rpc-url $RPC` before and after a `send` — watch gas leave acct #0.
- `cast call increment()` ten times, then `number()` — still 0? Why? (calls never persist.)
- `forge test -vvvv` — read a full execution trace, including the `emit`.
