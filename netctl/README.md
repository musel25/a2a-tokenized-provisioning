# netctl — the hands

gNMI provisioning library: `apply_bandwidth`, `apply_telemetry`, `teardown` (idempotent).
Topology-agnostic by rule (ADR-005): receives concrete device/interface names
(`ResolvedPath`/`ResolvedNode`), knows nothing about tickets, chains, or resource ids.

- Arrives: M3.1–M3.3 (Phase 3)
- May depend on: `interfaces`
