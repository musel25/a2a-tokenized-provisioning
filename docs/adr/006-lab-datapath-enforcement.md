# ADR-006 — Bandwidth enforcement in the containerized lab (the missing ASIC)

**Status:** accepted · 2026-07-07

## Context

M2.2 requires "iperf3 before ≫ after ≈ 50 Mbps" — a *physical* plateau, because the
thesis's central demo (and the M4.5 revocation showpiece) hinges on watching throughput
obey, and then lose, an on-chain entitlement.

Measured reality of containerized SR Linux (7220 IXR-D2L image, containerlab): the
control plane **accepts** QoS policer configuration, but the XDP software datapath does
**not enforce it** — a 100 Mbit/s UDP stream crosses a committed 50 Mbit/s policer with
0 % loss, and the policer's *state* tree reports `peak-rate-kbps 0`. Narrowing probes
showed the datapath enforces ACL match+**drop** but no rate-limiting of any kind, and
that `tc` ingress on the data ports is shadowed by XDP, while `tc` **egress** qdiscs on
the same ports do take effect (full table: docs/07 §6.2).

So the choice is about where the *missing ASIC half* of the policer lives.

## Decision

**The gNMI-committed policer config on srl1 remains the single source of truth; a piece
of lab infrastructure mirrors it into a `tc tbf` shaper inside srl1's own netns**
(`netlab/mirror-policer-to-tc.sh`; M3.2's fixtures loop it).

- The controller and `netctl` speak **only gNMI to the router** — rules 1–6 untouched.
  Neither ever learns the shim exists.
- Enforcement still happens **at the router** (same container, same netns, egress port),
  where the hardware ASIC would do it — the shim is the simulator's physics engine, not
  a new architectural component.
- The mapping is honest and documented: ingress policer on `ethernet-1/1.0` ⇒ egress
  tbf on `e1-2`, equivalent for hostA→hostB through a two-port router.

## Alternatives rejected

- **Config-plane-only evidence** (read back the committed policer, skip physics): kills
  the iperf plateau and the revocation demo — the two artifacts the plan says must never
  be cut (docs/01 §G).
- **`tc` driven directly by the controller/netctl**: enforcement would bypass the router
  entirely; rule 6 (netctl is gNMI-only) and the whole "the ticket configures a real
  router" story die.
- **A different NOS with an enforcing container datapath**: nothing viable fits — cEOS
  needs licensed images, VM-based NOSes don't fit the 14 GB lab machine, and SR Linux is
  the gNMI-native learning target.
- **7250/other SR Linux platform types**: measured — 7220 D1 exposes no QoS at all in
  the container, 7250 IXR-6e has no policer-templates (different QoS model) and crashed
  on this machine's RAM anyway.

## Consequences

- The lab needs a "shim tick" after policer changes (manual in M2.2, automated by the
  M3.2 fixture). Forgetting it = config says 50 Mbps, physics says unlimited — docs/07
  §6 lists this as the first thing to check when a plateau is missing.
- On real hardware the shim is simply not deployed; nothing else changes.
- Telemetry (M2.3) is unaffected: interface counters are maintained by the container
  datapath and stream fine over gNMI.
- The telemetry delivery-model decision the plan called "ADR-006" becomes **ADR-007**
  (docs/01 updated).
