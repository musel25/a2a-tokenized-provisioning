# contracts — the vending machine

Solidity settlement (Foundry): money moves and tickets exist here, nowhere else.
`A2ASettlement` is complete over M1.2–M1.4 (spec: invariants I1–I8, all green, in
[`docs/04-contract-spec.md`](../docs/04-contract-spec.md)): **M1.2** entitlement storage +
ERC-721 ownership · **M1.3** EIP-712 offers + atomic `fulfill` + the `consumed` ledger ·
**M1.4** `revoke`, `Revoked` event, on-chain `tokenURI`, and the real deploy script.
`Counter` is the M1.1 toolchain hello-world (its deployer: `script/DeployCounter.s.sol`).

```sh
forge test -vv                       # run tests (invariant-named: test_I2_…, test_I4_…)
anvil --timestamp 1757944500         # local pretend-chain at story time (separate terminal)
just deploy-local                    # from repo root: MockTOK + A2ASettlement
                                     #   → contracts/deployments/anvil.json
```

- solc pinned in `foundry.toml`; `lib/forge-std` is a git submodule of the parent repo

**Hands-on tours (beginner-first, in order):**
- [`EXPLORE.md`](EXPLORE.md) — M1.1: build, test, deploy, the call-vs-transaction experiment.
- [`EXPLORE-settlement.md`](EXPLORE-settlement.md) — M1.2: mint ticket #7, read it off the
  chain, prove a resale keeps the terms (I6). Concept companion:
  [`docs/04a-settlement-walkthrough.md`](../docs/04a-settlement-walkthrough.md).
- [`EXPLORE-fulfill.md`](EXPLORE-fulfill.md) — M1.3: be Bell and Ada — sign a real offer,
  redeem it, then cheat four ways and watch each named refusal (I2, I3).
- [`EXPLORE-revoke.md`](EXPLORE-revoke.md) — M1.4: decode the on-chain fine print, watch
  expiry do nothing, pull the kill switch (I4, I5, I7, I8).
