# contracts — the vending machine

Solidity settlement (Foundry): money moves and tickets exist here, nowhere else.
`A2ASettlement` is built over M1.2–M1.4 (spec: invariants I1–I8 in
[`docs/04-contract-spec.md`](../docs/04-contract-spec.md)): **M1.2 landed entitlement
storage + ERC-721 ownership**; `fulfill`/payment (M1.3) and revoke/`tokenURI` (M1.4)
follow. `Counter` is the M1.1 toolchain hello-world.

```sh
forge test -vv                       # run tests
anvil                                # local pretend-chain (separate terminal)
forge script script/Deploy.s.sol --rpc-url http://localhost:8545 \
  --private-key <anvil key 0> --broadcast
```

- solc pinned in `foundry.toml`; `lib/forge-std` is a git submodule of the parent repo

**Hands-on tours (beginner-first):**
- [`EXPLORE.md`](EXPLORE.md) — M1.1: build, test, deploy, the call-vs-transaction experiment.
- [`EXPLORE-settlement.md`](EXPLORE-settlement.md) — M1.2: mint ticket #7, read it off the
  chain, prove a resale keeps the terms (I6). Concept companion:
  [`docs/04a-settlement-walkthrough.md`](../docs/04a-settlement-walkthrough.md).
