# ADR-004 — Chain time is the canonical clock

**Status:** accepted · 2026-06-09

## Context
Two clocks exist: the chain's `block.timestamp` and the OS clocks of the controller and
routers. Entitlement validity (`startTime`/`endTime`), offer expiry (`validUntil`), and
proof expiry all need exactly one authoritative time source, or skew creates
heisenbugs ("works on my machine at 15:59").

## Decision
**All validity decisions are judged against chain time** (`block.timestamp`, read as the
latest block's timestamp via the `EntitlementReader.chain_time()` port):

- The contract checks `validUntil` at `fulfill` against `block.timestamp` (inherently).
- The controller's authorization predicate evaluates `startTime`/`endTime`, proof
  `expires_at`, and revocation against `chain_time()`.
- OS timers are **scheduling only**: a timer may wake the controller for teardown at `t1`,
  but the action re-verifies against chain time before executing.

## Consequences
- Deterministic and testable: Anvil supports time travel
  (`evm_setNextBlockTimestamp` / `anvil_setTime`), so expiry paths get real tests instead
  of `sleep()`.
- Matches on-chain semantics exactly — no "valid on chain, expired at the controller"
  inconsistency.
- Minor: on a quiet Anvil the latest block can be old; tests mine a block (or use
  interval mining) before reading time.
