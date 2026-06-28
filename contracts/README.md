# contracts — the vending machine

Solidity settlement (Foundry): money moves and tickets exist here, nowhere else.
The real `A2ASettlement` arrives at M1.2–M1.4 (spec: invariants I1–I8 in
`docs/01-implementation-plan.md`, Phase 1 opener); the present `Counter` is the
M1.1 toolchain hello-world.

```sh
forge test -vv                       # run tests
anvil                                # local pretend-chain (separate terminal)
forge script script/Deploy.s.sol --rpc-url http://localhost:8545 \
  --private-key <anvil key 0> --broadcast
```

- solc pinned in `foundry.toml`; `lib/forge-std` is a git submodule of the parent repo

**Hands-on tour:** [`EXPLORE.md`](EXPLORE.md) — build, test, deploy, and the
call-vs-transaction experiment, step by step.
