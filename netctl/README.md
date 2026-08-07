# netctl — the hands

gNMI provisioning library: topology-agnostic by rule (ADR-005) — it receives concrete
device/interface names (`ResolvedPath`/`ResolvedNode`) plus a device→endpoint map, and
knows nothing about tickets, chains, or resource ids.

- **M3.1** `gnmi_smoke` — Get/Set/Get-back, and the TLS trust-on-first-use recipe
  (`connect.py`) every later piece reuses.
- **M3.2** `GnmiProvisioner` (`apply_bandwidth`/`teardown`, stateless + idempotent —
  sessions leave *names* on the router, not state in the process) beside
  `MockProvisioner` (the skeleton's FakeNet, promoted). One shared contract suite runs
  against both — rule 7 as a test file.
- M3.3 `apply_telemetry` follows (ADR-007).

```sh
uv run pytest netctl/                 # mock leg always; gnmi leg when the lab is up
uv run python -m netctl.gnmi_smoke    # three exchanges against the live router
```

**Hands-on tour:** course chapter [`06`](../e2e/notebooks/course/06_the_hands_and_the_invariance_bet.ipynb) —
the same gNMI calls made by hand, the config read back off the router, and the
invariance bet experienced.
