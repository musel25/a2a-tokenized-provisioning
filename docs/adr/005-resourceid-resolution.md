# ADR-005 — Controller resolves resourceId; netctl stays topology-agnostic

**Status:** accepted · 2026-06-09

## Context
Entitlements carry an abstract `resourceId` (32 opaque bytes). Somewhere it must become
concrete: which device, which interfaces. Candidates: the contract (too rigid, leaks
topology on-chain), `netctl` (would couple the gNMI layer to one lab), or the controller.

## Decision
The **controller** owns the mapping, as a config file (`controller/resource_map.yaml`:
`resourceId → {device, ingress_if, egress_if}` or `{device}`). Its translators resolve the
id and pass **concrete targets** (`ResolvedPath` / `ResolvedNode`) through the provisioning
port. `netctl` receives device and interface names and speaks gNMI — it knows nothing about
resource ids, entitlements, or the chain.

## Consequences
- `netctl` is reusable against any topology and trivially mockable — it is "hands", not
  "brain".
- Topology changes touch exactly one file.
- This is the anti-corruption layer doing its job: the settlement model's vocabulary
  (resourceId) never leaks into the network layer, and YANG paths never leak upward.
- Note for readers: in this project **ACL = anti-corruption layer** (DDD), not
  access-control list.
