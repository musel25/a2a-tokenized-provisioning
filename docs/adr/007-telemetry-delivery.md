# ADR-007 — Telemetry delivery: a provider-side forwarder

**Status:** accepted · 2026-07-07

## Context

gNMI telemetry is **dial-in**: the collector connects to the router and subscribes
(M2.3 did exactly that by hand). But the product Ada bought (docs/03 §1.3, story ch. 7)
is "samples arrive at MY endpoint" — she names a `collector_endpoint`, she doesn't ask
for router credentials. Someone has to bridge the direction mismatch.

## Decision

**`apply_telemetry` runs a provider-side forwarder** (option (a), the plan's default
leaning): netctl subscribes to the router over gNMI (dial-in, provider credentials,
inside the provider's domain) and relays each update to the consumer's endpoint as one
`TelemetrySample` JSON line over TCP (shape: docs/03 §5.1, `a2a_interfaces`).

- The consumer's experience matches the purchase: samples arrive at the endpoint in
  the entitlement, no router access, no gNMI knowledge, no credentials handed out.
- The router stays sealed: only netctl (provider side) ever dials it — consistent with
  rule 6 and with how a provider would actually run this.
- Teardown = stop the forwarder; the router subscription dies with it.

## Alternatives rejected

- **(b) consumer dials in directly** ("activation" = opening gNMI access + handing over
  connection details): leaks provider credentials/topology to the consumer, needs
  per-session ACL management on the router, and makes revocation depend on the
  consumer's cooperation. The one advantage (no forwarder process) isn't worth it.
- **Push samples on-chain / via the controller**: the chain is a clock and a ledger,
  not a data plane; the controller authorizes, it must not become a traffic proxy.

## Consequences

- The forwarder is **process state** (unlike bandwidth config, which lives on the
  router): if the provisioner process dies, forwarding stops until re-applied. Honest
  v0 limitation, noted in the provisioner docstring; a real deployment supervises the
  forwarder like any service.
- The wire format to the collector is a cross-package shape → `TelemetrySample` lives
  in `a2a_interfaces` (rule 3) and is documented in docs/03 §5.1.
- MockProvisioner records `apply_telemetry` calls exactly like bandwidth ones; the
  shared contract suite (rule 7) grows telemetry legs for both implementations.
