# 09 — Evaluation: is this architecture feasible, and at what cost?

> **Status:** the evaluation chapter. Every number is real, produced by `e2e.experiments`
> against the live stack. Reproduce with §11; raw data in `e2e/runs/eval/*.jsonl`, figures
> in [`e2e/notebooks/evaluation_explore.ipynb`](../e2e/notebooks/evaluation_explore.ipynb).
> These results were adversarially audited by a review panel before writing; the
> corrections it forced are folded in (and noted where they matter).

## 1. What the PoC proves, and what an evaluation adds

The proof-of-concept is an **existence proof**: agents negotiate over A2A, pay atomically
for an ERC-721 entitlement, and a deterministic controller honors it by configuring a real
SR Linux router. That shows the architecture *can be built*. It does not, alone, say
whether it is any good — that needs numbers, each attached to a question a skeptical
examiner would push on. Seven experiments provide them. The boundaries they expose matter
as much as the successes, so they are stated throughout, not buried.

## 2. Two definitions, fixed up front (so nothing is smuggled)

- **"Enforced on the device"** means: the policer (bandwidth) or dial-out export
  destination (telemetry) was **committed via gNMI Set and read back from srl1's running
  config**. It does **not** mean packets were observed being rate-limited — containerized
  SR Linux does not enforce QoS in its datapath (**ADR-006**). Datapath proof is separate:
  the `just console` iperf plateau (100→49 Mbps) shown live. Every "enforced" below carries
  this meaning.
- **The stack is real; five things are simulated**, and each caps a specific claim:
  (1) Anvil **auto-mines instantly** → measured chain latency is a lower bound; (2) all
  components are **co-located and called in-process** (no A2A/HTTP hop in the timed path)
  → latencies are a transport-free lower bound; (3) the **datapath carve-out** above;
  (4) **n=20 sequential, single machine, single run, warm** → medians characterize typical
  cost, not tails or throughput; (5) **one LLM** (Qwen3-4B) on **one Modal deployment, one
  session**. No component was mocked — that pairing of a real stack with named simulation
  boundaries is where the credibility comes from.

## 3. Headline result

**Feasible for tokenized network-service provisioning at window/lease timescales.** The
deterministic, security-bearing code this thesis contributes runs in **~90 ms** end to end
and its authorization decision costs **~90 nanoseconds**; making provisioning trust-minimized
adds **~69 ms** over a bare device write. The visible cost of an *agent market* is the LLM
round-trips (~3.3 s) and, on a public chain, block confirmation — both **pluggable policy
choices**, not properties of the design. **80/80 lifecycles completed with zero failures.**

## 4. Where the time goes (E1 — latency, n=20 per mode×service)

Phase-timed request→enforced. `activate()` runs the predicate *and* the gNMI Set, so we
split *controller compute* from *actuate*. We report **median with [min, max]**; at n=20 a
"p95" is essentially the max, so we don't cite one (a bug that had made it *exactly* the
max was caught in audit and fixed).

| phase | det/bandwidth | trust domain |
|---|---:|---|
| negotiate (judgment) | 0 (det) · **3.05 s** (llm: quote 1.41 s + decide 1.64 s) | agents (LLM) |
| sign (EIP-712 + EIP-191) | ~6 ms | crypto |
| settle (chain, instant-mine) | 38 ms | chain |
| controller compute (+ chain reads) | ~23 ms | controller |
| actuate (gNMI → srl1) | 21 ms | network |
| **end to end** (det, pooled n=40) | **89 ms** [68–129] | |
| **end to end** (live LLM, n=40) | **3.27 s** [3.10–3.62] | |

Telemetry tracks bandwidth within a millisecond per phase — the "same machine, one
translator" result (M6.3), quantified. **The det path skips negotiation entirely** (fixed
canonical price; there is no deterministic consumer graph — the production consumer always
calls the LLM), so the 3.2 s det→llm delta *is* the full cost of the two judgment slots on
this model, and that latency is a property of the model/deployment, not the architecture.

**Caveat (audit):** 89 ms is a **transport-free, in-process, instant-mine lower bound** on
the protocol's compute. On a real deployment, add per-hop A2A/HTTP RTT and block time (§6b).

## 5. The authorization predicate costs ~90 nanoseconds (E7 — the sharpest number)

`controller.domain.predicate` is a pure function over an `EntitlementView` — zero I/O
(rule 4), verified by import. Timed in isolation (200k calls per outcome):

| outcome | ns/call | | outcome | ns/call |
|---|---:|---|---|---:|
| **allow** (all 6 checks) | **86** | | E_REVOKED | 70 |
| E_NOT_OWNER | 51 | | E_SCOPE | 79 |
| E_NOT_STARTED | 56 | | E_CONFLICT | 83 |
| E_EXPIRED | 65 | | | |

**Claim it defends:** the security-critical judgment the thesis insists must be
deterministic (rule 1) is *not a bottleneck by three orders of magnitude* — the whole
authorization decision is ~90 ns, versus ~1.6 s for the LLM slots and tens of ms for chain
and gNMI. This is the strongest data-backed form of "the architecture's own contribution is
free"; it isolates the predicate from the chain-reads and gNMI that `activate_s` bundles.

## 6. The entitlement physically governs the wire (E2 — chain-time enforcement)

ADR-004: chain time is the only clock. Two lags show the ticket's on-chain state drives the
device (config-committed sense, §2):

- **Revocation lag** — on-chain `revoke` mined → policer gone from srl1, via the *real*
  polling watcher (`chainmcp` `watch_revoked` → `controller` `handle_revoked` → gNMI
  delete): **464 ms median** pooled (n=80), range [237, 647] at poll = 0.5 s.
- **Expiry lag** — chain time passes `end_time` → the ExpiryTimer's tick tears down:
  **73 ms median** [65, 85] (a single synchronous gNMI delete).

**Revocation lag is poll-bounded, not fixed** (E9 sweep — this defuses "your number is just
your polling choice"):

| watcher poll | 0.1 s | 0.25 s | 0.5 s | 1.0 s | 2.0 s |
|---|---:|---:|---:|---:|---:|
| revocation lag (median) | 182 ms | 248 ms | 508 ms | 990 ms | 1999 ms |

Lag ≈ **poll interval + ~80 ms actuation floor**: a *tunable operator SLO knob* (the poll)
plus an *architectural minimum* (the gNMI teardown + detection). On a public chain, add
event-visibility delay (block time) — the same extrapolation caveat as settlement.

**Claim it defends:** revocation and expiry are enforced on real hardware within a bounded,
tunable lag whose floor is one device round-trip — the entitlement is authorization, not
paperwork.

## 7. What it costs (E3 — gas → dollars, per service type)

Execution `gasUsed` measured on a local EVM (Anvil — exact for these contracts at the
pinned solc/hardfork). **Reported per service** because fulfill is bimodal: telemetry offers
carry much larger ABI-encoded params (a pooled median would describe no real transaction).

| op | bandwidth (gas) | telemetry (gas) |
|---|---:|---:|
| fulfill (buyer-paid: mint + settle) | 268,050 [268k–319k] | 447,371 |
| revoke (issuer-paid) | 29,903 | 29,903 |
| approve (one-time ERC-20 setup) | 46,366 | 46,366 |

**Independent cross-check:** `forge snapshot` over the Foundry tests reports fulfill at
324k–347k gas (different offer fixtures + storage warmth than the warm-path harness runs);
both agree to the same order, ~2.7–4.5 × 10⁵ gas. Dollar cost of a *bandwidth* fulfill
(ETH \$3000, illustrative, 2026-07; **on L2 add an unmeasured L1 data-fee for calldata**):

| | L2 @ 0.03 gwei | L1 @ 8 gwei | L1 @ 30 gwei |
|---|---:|---:|---:|
| bandwidth fulfill (268k) | ~\$0.024 | ~\$6.4 | ~\$24 |
| telemetry fulfill (447k) | ~\$0.040 | ~\$10.7 | ~\$40 |

**Claim & boundary:** economically feasible on any rollup (a few cents), where the whole
trust-minimized flow also completes in ~2 s (§6b). On L1 a provisioning is \$6–40, which
*shapes the product* — lease longer windows to amortize, don't price per-flow. A clean
feasibility boundary, not a failure.

### 6b. Chain latency, extrapolated (analytic, not measured)

Anvil mines instantly, so measured settle (~38 ms) and the "~69 ms trustlessness overhead"
(§9) are compute-only lower bounds. First-order extrapolation:

| chain | settle wait | full provisioning (det compute + settle) |
|---|---|---|
| Anvil (measured) | instant | ~0.09 s |
| L2 rollup (~1 block) | ~2 s | ~2.1 s |
| Ethereum L1 (1 conf) | ~12 s | ~12 s |
| Ethereum L1 (finality) | ~13 min | ~13 min |

Feasible at provisioning (minute) timescales; unfit for real-time per-flow admission on L1.

## 8. It cannot be cheated — within its threat model (E4 — adversarial matrix)

Twelve attacks drawn from the documented threat model, each run end-to-end on the real
stack and attributed to the layer that rejected it. **Every one was rejected at its designed
layer** (3 at the contract, 9 at the controller; predicted layer == actual layer in all 12):

| attack | rejected by | code |
|---|---|---|
| replay a consumed offer (same salt) | contract | `OfferAlreadyUsed` |
| forged provider signature | contract | `BadSignature` |
| fulfill a lapsed offer (`valid_until` past) | contract | `OfferExpired` |
| activate before the window opens | controller | `E_NOT_STARTED` |
| proof signed by a non-owner | controller | `E_NOT_OWNER` |
| garbage activation signature | controller | `E_NOT_OWNER` |
| replay a consumed challenge nonce | controller | `E_NONCE_REUSED` |
| activate the same ticket twice | controller | `E_CONFLICT` |
| telemetry action on a bandwidth ticket | controller | `E_SCOPE` |
| activate a revoked ticket | controller | `E_REVOKED` |
| challenge a nonexistent ticket | controller | `E_UNKNOWN_ENTITLEMENT` |
| activate after the window ends | controller | `E_EXPIRED` |

Two layers, independent: the chain rejects bad *money* (forged / replayed / expired offers)
with no controller; the controller rejects bad *access* (owner / nonce / time / scope /
revocation) without trusting the agent. Defenses are deterministic code (rule 1).

**Honest scope (audit):** these are *enumerated tests of known guards written by the
system's author*, not a fuzzing or economic adversary. Rejection is raised **upstream of any
gNMI call** in the code path — so no rejected attack configured the device — but this is an
architectural property of where the checks sit, not a per-attack device readback. **Untested
attack classes** (named as future work): input fuzzing, chain-level adversaries
(front-running fulfill, a reorg racing the revocation watcher), and malformed-parameter
translation. One case is **allowed by design**: a *second valid ticket on the same resource*
activates and **does** configure the device — per-resource capacity is the provider's
`CapacityLedger` concern at quote time (tested in M5.2), not a controller security check;
the controller's `E_CONFLICT` is strictly per-ticket.

## 9. The price of trustlessness (E6 — baseline)

The same 50 Mbps path provisioned with **no agents, no chain, no controller** — one direct
`netctl` call — takes **20 ms**. The full deterministic lifecycle takes 89 ms. So trust-
minimization adds **~69 ms**, which decomposes as: on-chain settle ~38 ms (instant-mine
lower bound) + signing (offer + proof) ~6 ms + challenge + controller compute + chain reads
~23 ms. **The authorization predicate itself is <0.1 µs** (§5) — the security *logic* is
free; the ~69 ms is settlement, signatures, and the controller's own chain reads, most of
which is the (here-instant) chain write.

## 10. The judgment layer (E5 — LLM), reported precisely

Two slots against the deployed Qwen3-4B, one session:

- **Quote** (Bell prices): **10/10 schema-valid, first attempt, 0 retries**, all in the
  [5,25] TOK band. But **every quote was exactly 10 TOK** across needs spanning 10–500 Mbps
  — the model *anchored to the stated list price* and showed **no capacity-dependent
  pricing**. So this validates **schema + constraint compliance**, not price discovery; any
  "prices vary" claim would be false on this data. (~1.45 s, ~276 tokens/call.)
- **Decide** (Ada accept/reject, graded vs ground-truth *accept-iff-affordable*): **12/12
  correct** (9/9 excluding the 3 `price==budget` boundary cases, whose accept-at-equality
  convention is a prompt choice). This is a **curated smoke test of a one-comparison
  function**, single sample per case — it shows the model handles clean threshold decisions
  and the validate-and-retry guard returns a valid object or a safe *decline*, never a
  hallucinated shape. It is **not** a robustness benchmark (no malformed offers, no repeated
  sampling). (~1.65 s, ~838 tokens/call.)
- **Cost per negotiation:** quote + decide ≈ **1114 tokens** → **\$0.0002–0.002** at
  \$0.20–2.00/Mtok. Negotiation overhead is a fraction of a cent — far below any plausible
  service price.

**Claim it defends:** an agent-to-agent market is viable — the decision layer is accurate on
unambiguous cases, fails safe, and costs almost nothing per negotiation. **Boundary:** one
model, one session; pricing judgment specifically was *not* demonstrated.

## 11. Threats to validity (consolidated)

| threat | honest framing |
|---|---|
| n=20, single machine, one run, warm, sequential | medians of a low-variance mechanical pipeline; supports *order-of-magnitude* per-lifecycle cost, **not** tails or throughput/concurrency (never measured) |
| Anvil instant-mine | chain latency is a lower bound; consensus latency is extrapolated (§6b), a property of the chosen chain |
| in-process, co-located components | 89 ms excludes A2A/HTTP serialization + network hops; a transport-free lower bound |
| ADR-006 datapath carve-out | "enforced" = config committed + read back, not packets shaped; datapath proof is the separate console iperf plateau |
| adversarial = enumerated own-threat-model tests | every documented guard fires at its layer; fuzzing / reorg / economic adversaries untested |
| LLM = one model, one session, single-sample | latency/accuracy attributed to this deployment; quote pricing is anchor-echoing, not discovery |
| gas on Anvil | execution gas exact for pinned solc; L2 user-fee adds an unmeasured L1 data-fee component |

## 12. Conclusions

The evaluation supports a **bounded** feasibility claim:

1. A trust-minimized provisioning completes in **89 ms** (deterministic) / **3.3 s** (live
   LLM), request → enforced (config-committed) on a real router; **80/80 runs, 0 failures.**
2. The **authorization predicate costs ~90 ns**; trust-minimization adds **~69 ms** over a
   bare device write (settle + signatures + chain reads) — the security logic is free.
3. On-chain revocation is enforced in **~464 ms** at a 0.5 s watcher poll, **scaling
   linearly with the poll** (a tunable SLO knob + ~80 ms floor) — the ticket governs the wire.
4. **12/12 threat-model attacks rejected** at their designed layer (3 contract / 9
   controller), upstream of any device write.
5. A provisioning costs **268k gas** (bandwidth) / **447k** (telemetry) — a few cents on an
   L2, \$6–40 on L1 — feasible on any rollup.
6. LLM decisions are **12/12 correct** on curated cases with a fail-safe guard, at **~1114
   tokens (<1¢) per negotiation** — an agent market is viable.

**Boundaries, stated plainly:** feasible for provisioning at minute timescales, **not**
real-time per-flow setup on L1; enforcement measured as config-on-device (ADR-006; the
console iperf plateau is the datapath proof); chain latency and L1 fees extrapolated, not
measured; n=20 single-machine (no throughput/tail claims); adversarial coverage limited to
the documented threat model; LLM pricing not demonstrated. Within those bounds, the
architecture does what the thesis claims — and the deterministic, trust-critical core it
contributes is, by three orders of magnitude, not the thing that costs anything.

## 13. Reproduce

```sh
containerlab deploy -t netlab/topology.clab.yml           # the router
set -a && source .env && set +a                           # for --mode llm (deployed model)
uv run python -m e2e.experiments --exp all --n 20         # latency+expiry+baseline+adversarial+llm
uv run python -m e2e.experiments --exp predicate          # E7 (no lab/chain needed)
uv run python -m e2e.experiments --exp revlag_sweep       # E9 (lab; ~15 min)
uv run --group demo jupyter nbconvert --to notebook \
  --execute --inplace e2e/notebooks/evaluation_explore.ipynb   # the figures + tables
```

Deterministic-only (faster, no `.env`): `--mode det`. Data: `e2e/runs/eval/*.jsonl`
(committed as evidence). Contract-gas cross-check: `cd contracts && forge snapshot`.
