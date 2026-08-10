# ADR-008 — Telemetry delivery: the tunnel, and what the tunnel exposes

**Status:** accepted · proposed 2026-08-07, implemented 2026-08-10 (M7.2) ·
supersedes ADR-007's "out of scope for v0" consequence

## Context

ADR-007 decided *what the telemetry ticket buys*: the right to have one specific
configuration written to the router. That decision stands. What it left open was whether
the written config ever produces a sample at a collector — recorded honestly at the time
as "the export connection itself needs a tunnel server to complete — out of scope for
v0," and carried into the paper as a measurement boundary: bandwidth is verified to the
dataplane (the ADR-006 shim, a 48 Mbit/s plateau), telemetry only to the config plane.

That asymmetry is what this ADR closes. Half of it was the known missing piece — no
tunnel server existed. The other half was not known and is the substantive finding.

## What the probe measured (2026-08-07, lab up, srl1 = 7220 IXR-D2L container)

**SR Linux splits dial-out into two nodes, and `apply_telemetry` writes only the inert
one.**

| node | what it is | schema |
|---|---|---|
| `/system/grpc-tunnel/destination[name]` | an address-book entry | `address`, `port`, `network-instance`, `tls-profile` — **no admin-state, no oper-state** |
| `/system/grpc-tunnel/tunnel[name]` | the active half: dials, registers, carries sessions | `admin-state`, `oper-state`, `oper-state-down-reason`, `destination*`, `target*` |

`provisioner.py::apply_telemetry` writes the destination and stops. So even with a tunnel
server listening, the committed config could never have dialed. The destination survives
`delete tunnel` with delivery stopped — which is the direct proof that it is inert.

Three further lab facts, each of which independently blocks the loop:

1. **The CPM filter is a stateless port allow-list applied in both directions.** Entry 60
   permits `destination-port 22`; entry 70 separately permits `source-port 22` — the
   explicit return-path rule. Outbound dial-out therefore needs its own `source-port
   <collector>` accept, or entry 1000 "Drop all else" eats the SYN-ACK. Observed as TCP
   stuck in SYN_RECV with entry 1000's `matched-packets` climbing.
2. **SR Linux dials the tunnel in plaintext** when the destination has no `tls-profile`.
   A TLS-enabled tunnel server closes the socket (`UNAVAILABLE: Socket closed`).
3. **The collector must sit on the lab bridge**, not the host: bridge→host is dropped on
   this machine, bridge→container is not.

With those corrected, the loop closes and delivery is *causally gated by the config the
entitlement authorized*:

```
tunnel up:      in-octets 782569785 → 813087483 → 853900381 → 883780685   (5 s beat, under iperf load)
delete tunnel:  0 samples in the following 20 s
```

**What the tunnel exposes.** The target type that makes this work is
`gnmi-gnoi-server <grpc-server-name>`: the router dials out and hands the collector a
session onto a gRPC server instance. Bound to `mgmt`, that instance carries `[gnmi, gnsi]`
— and gNMI includes `Set`. A consumer who bought monitoring would receive a path to the
router's configuration service, gated only by credentials.

Role-based read-only was measured and **does not work on this image**:

| test (non-superuser role, `services [gnmi]`) | result |
|---|---|
| `Set /interface[...]/description` | `PermissionDenied` ✓ |
| `Get` on statistics, oper-state, host-name | **all empty** ✗ |
| `cli allow-command-list` grants | no effect on gNMI reads |

A non-superuser gets no read access at all. Fine-grained per-path read authorization
lives in gNSI **pathz**, which is installed over the gNSI Pathz RPC — present in the
`grpc-server services` enum, but not configurable through CLI or gNMI Set, and needing a
gNSI client this project does not have.

## Decision

**1. `apply_telemetry` writes both nodes.** Destination `a2a-<sid>` as today, plus tunnel
`a2a-<sid>` referencing it, with a target whose type is `gnmi-gnoi-server` bound to a
dedicated server instance (below). Teardown deletes **tunnel first, then destination** —
the same leafref-ordering lesson as the policer attachment (`_session_config_on`).

**2. Tunnel targets bind to a dedicated `grpc-server telemetry` instance with
`services [ gnmi ]`.** This removes gNOI entirely from the tunneled session — no
`reboot`, `factory_reset`, `file`, or `os`. Verified: the tunnel reaches `oper-state up`
and streams samples when bound to this instance rather than `mgmt`.

**3. `Set` over the tunnel remains credential-gated, and this is documented, not hidden.**
gNSI pathz is the standards-track fix and is named as future work, with the measured
evidence above for why the cheaper role-based route is not available here.

**4. The lab gains a collector node and the CPM return-path rule** — the collector is the
consumer's, correctly modeled as a node on the bridge; the CPM entry goes in
`srl1-init.cli` with a comment explaining the stateless-both-directions behavior, exactly
as ADR-006's shim is documented rather than hidden.

Rule 6 is untouched: `netctl` still speaks only gNMI to the router and learns nothing
about tickets or topology. No `a2a_interfaces` shape changes — `apply_telemetry`'s
signature is unchanged, so no `v` bump.

## Alternatives rejected

- **A dial-in collector** (subscribe to srl1 from a lab node, print samples). Cheap, and
  proves nothing: samples would flow because the collector dialed in, not because the
  ticket was honored. Evidence-shaped decoration, strictly worse than the honest gap.
- **Role-based read-only user.** Measured above: denies `Set` correctly but also denies
  every read. Not usable on this image.
- **gNSI pathz now.** The right long-term answer, and it would scope the tunnel principal
  to `Subscribe`/`Get` on the entitlement's sensor paths. Deferred: new tooling, unknown
  depth on this image, and it is separable from the delivery result.
- **Provider-side forwarder.** Already rejected in ADR-007 and still rejected for the same
  reason — it delivers data when the product is a config right, and it is process state
  rather than durable on-device config.

## Consequences

- The paper's telemetry/bandwidth asymmetry closes: both services now carry evidence past
  the config plane. The abstract's "two services" becomes evidentially symmetric.
- ADR-007's Consequences bullet ("out of scope for v0") is superseded; its Decision is not.
- The lab needs the CPM entry, like it needs the ADR-006 shim tick — on real hardware
  neither is deployed. Both belong in the same "first thing to check" list in docs/07.
- Teardown gains an ordering constraint (tunnel before destination) and the shared
  contract suite must assert it against both `GnmiProvisioner` and `MockProvisioner`.
- A stale `destination a2a-ent8-a1` was found on the router from an earlier session.
  Whether teardown ran at all for that session is unverified — check during
  implementation before concluding anything about rule 8.

## What implementation changed (2026-08-10, M7.2)

Three amendments to the Decision, each because the lab said so:

1. **The ordering assertion did not go into the shared contract suite.** Delete order is
   invisible at the port — `MockProvisioner` has no delete list — so asserting it "against
   both" would have meant inventing mock state that models nothing. It is a gNMI-only unit
   test over a stubbed client, beside the existing gNMI-only `test_unknown_device_is_a_loud_error`.
   What the shared suite *did* gain is the two-node meaning of "applied": the mock records
   `nodes: (destination, tunnel)` so that a provisioner writing one node goes red on both legs.
2. **TLS runs in opposite directions on the two hops.** The tunnel transport is plaintext
   (a TLS listener meets SR Linux's plaintext dial with `UNAVAILABLE: Socket closed`), but
   the gNMI session *inside* the tunnel terminates on the router's grpc-server, which
   serves TLS — a plaintext client there fails as `error reading server preface: EOF`.
   So: no TLS on the collector's tunnel-server, skip-verify on its client half.
3. **The stale `a2a-ent8-a1` destination is explained, not a rule-8 violation.** It was
   written by the destination-only code path, which had no tunnel to delete and left the
   inert half behind on a teardown that predated `_session_telemetry_on` knowing about
   tunnels. Teardown now finds and removes both nodes; verified by readback.

Measured after implementation, collector listening throughout:

| shape written | samples at the collector |
|---|---|
| destination alone (the ADR-007 shape) | **0 in 20 s** |
| destination + tunnel (this ADR) | flowing, `oper-state up`, in-octets 339400934 → 379948882 → 419836726 → 460628428 → 473008756 on a 5 s beat under iperf load |
| after `teardown` | **0 in 20 s**, no config left on the router |

The first row is the finding this ADR exists for: with a live collector on the other end,
the config the prototype used to write delivered nothing.
