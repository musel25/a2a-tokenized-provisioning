# ADR-007 — Telemetry as a device-config right (revised from a forwarder)

**Status:** accepted · 2026-07-07 · **revised** 2026-07-07 (see "Revision")

## Context

gNMI telemetry is **dial-in**: the collector connects to the router and subscribes
(M2.3 did exactly that by hand). The first cut of this ADR treated the product as
"samples arrive at MY endpoint" and bridged the direction mismatch with a provider-side
forwarder. That framing turned out to miss the point of the token.

## Revision — what the telemetry ticket actually buys

The telemetry product is **the right to push a telemetry configuration to the device** —
not the data. The token *is* the access: holding a valid telemetry entitlement is what
lets the router be configured to export monitoring. This makes telemetry **symmetric with
bandwidth**, which was already this exact shape:

| ticket | the right to write, to the router… | proof it was honored |
|---|---|---|
| bandwidth | a rate **policer** (`/qos`) | read the policer back off srl1 |
| telemetry | a **dial-out export destination** (`/system/grpc-tunnel/destination`) | read the destination back off srl1 |

Both are: *the token authorizes the controller to write one specific config to the device;
the config lives ON the router (readable back); teardown removes it.*

## Decision

**`apply_telemetry` writes a real gNMI export destination to the router** — SR Linux's
`grpc-tunnel destination[name=a2a-<session>]` pointing at the consumer's collector
(`address`/`port`/`network-instance`). The router dials out to that collector; the
consumer never receives router credentials — the controller (rule 2) is the only writer,
and the ticket is what authorizes the write.

- The consumer's experience matches the purchase: they bought the *right to configure
  telemetry export*, and a config with their collector now exists on the device.
- Teardown is **stateless and on-device** (like the policer): the destination named
  `a2a-<session>` is found on the router and deleted — a second call is the same success
  (rule 8). No provider process to supervise; survives a provisioner restart.
- `MockProvisioner` records `apply_telemetry` exactly like bandwidth; the shared contract
  suite (rule 7) asserts the config-write/teardown roundtrip for both implementations.

## Alternatives rejected

- **Provider-side forwarder** (the original decision): netctl subscribes to the router
  and relays `TelemetrySample` lines to the consumer's endpoint. Rejected on revision —
  it delivered *data* when the product is *the right to configure the device*, and it was
  process state (forwarding stopped if the process died) rather than durable on-device
  config. Removed (`netctl/forwarder.py` deleted). `TelemetrySample` remains in
  `a2a_interfaces` as the wire shape a collector parses if one is wired up.
- **Consumer dials in directly** (hand the consumer gNMI access): leaks provider
  credentials/topology and makes revocation depend on the consumer. The controller-writes
  model keeps the router sealed and revocation one-sided.
- **Push samples on-chain / via the controller**: the chain is a clock and a ledger, the
  controller authorizes — neither is a data plane.

## Consequences

- SR Linux has no consumer-facing "stream sensor X to collector Y" persistent config; the
  `grpc-tunnel` dial-out destination is the closest real, writable, readable analog, and
  the demo's point is that *the config lands because the ticket authorized it* (the export
  connection itself needs a tunnel server to complete — out of scope for v0).
- The M6.3 "how little changes between the two service types" result stands and is
  *stronger*: both translators now produce a device-config write, differing only in which
  subtree and payload — one `translate_bandwidth` vs `translate_telemetry`.
