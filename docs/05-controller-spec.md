# 05 — Controller spec: the bouncer's rulebook (Phase 4)

> **Status:** living — opened at the start of Phase 4, filled in as M4.1 → M4.5 land.
> Every rule here has (or will have) a named test next to it; an untested rule is a claim.
> **Companions:** `docs/03-interfaces.md` §3/§4/§5 (the surfaces this implements) ·
> DESIGN.md §7.4 (the predicate's origin) · `CLAUDE.md` rules 1, 4, 5, 6.
> *(Numbering note: coexists with `05-from-scratch.md`, same precedent as the two 04s.)*

---

## 1. What the controller is (and is not)

The controller is the **deterministic gatekeeper** between promises (chain) and physics
(routers): it verifies that the requester owns a valid entitlement and, only then, moves
the network. It is **never an LLM and never calls one** (rule 1) — every decision below
is a pure function anyone can replay. It holds **no keys** (rule 2): it verifies
signatures, it never signs.

## 2. The predicate (M4.1) — verbatim contract

```
predicate(view: EntitlementView, owner: str, requester: str, now: int,
          active_ids: set[int]) -> ErrorCode | None
```

Six checks, **in this order**, first failure wins (docs/03 §3.4 codes):

| # | Check | Denial |
|---|---|---|
| 1 | requester == owner (`ownerOf` on chain) | `E_NOT_OWNER` |
| 2 | now ≥ startTime | `E_NOT_STARTED` |
| 3 | now < endTime | `E_EXPIRED` |
| 4 | not revoked | `E_REVOKED` |
| 5 | serviceType has a translator | `E_SCOPE` |
| 6 | id ∉ active_ids (no double-booking) | `E_CONFLICT` |

`now` is **chain time**, always (ADR-004). The predicate is pure: no I/O imports in its
module — enforced by an executable test that inspects the imports (M4.1).

## 3. The session state machine (M4.1)

```
requested ──authorize──▶ authorized ──provision_ok──▶ active ──teardown──▶ torn_down
     │                        │                          │
     └──deny──▶ failed ◀──provision_failed──────────────┘ (teardown of a failed/torn
                                                            session: stays put — idempotent)
```

Transitions are DATA (a dict), not `if`-chains; illegal transitions raise. `torn_down`
and `failed` are terminal (re-teardown is absorbed, rule 8).

## 4. Challenge–response auth (M4.2)

Per docs/03 §3.2: nonce issued per challenge (single-use, expiry vs **chain time**),
proof = EIP-191 signature over `a2a-activate|{controller_id}|{nonce}|{entitlement_id}|{expires_at}`,
recovered address must equal `ownerOf(entitlement_id)`. Replay → `E_NONCE_REUSED`;
stale → `E_BAD_PROOF`; wrong signer → `E_NOT_OWNER`… exact mapping pinned by tests.

## 5. Translators (M4.3)

Pure functions `EntitlementView + resource_map → [ProvisionerCall]`, one per
serviceType; golden-file tests pin exact expected call lists (reviewed once by eye,
guarded forever). The `resourceId → topology` map lives in `controller/resource_map.yaml`
(ADR-005) and is the ONLY place ids meet devices.

| serviceType | translator input | provisioner calls |
|---|---|---|
| 0 bandwidth | BandwidthParams + ResolvedPath | `apply_bandwidth(sid, path, capacity_bps, qos_class)` |
| 1 telemetry | TelemetryParams + ResolvedNode | `apply_telemetry(sid, node, paths, endpoint, interval)` |

## 6. HTTP API (M4.4)

docs/03 §3 exactly; the API layer contains **no logic** — parse, call domain, map
`ErrorCode` → HTTP status. An `if` about entitlements in the API layer is in the wrong
file.

## 7. Wiring + watchers (M4.5)

ChainClient (read-only) + GnmiProvisioner + resource_map composed into the app;
`watch_revoked` → teardown; an asyncio expiry task that wakes near t1 and **re-checks
chain time before acting** (ADR-004 in code). The showpiece: on-chain `revoke` kills a
live lab session mid-window.
