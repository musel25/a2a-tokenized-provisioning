# 09 — Evaluation: is this architecture feasible, and at what cost?

> **Status:** the evaluation chapter. Every number is real, produced by `e2e.experiments`
> against the live stack. Reproduce with §13; raw data in `e2e/runs/eval/*.jsonl`, figures
> in [`e2e/notebooks/evaluation_explore.ipynb`](../e2e/notebooks/evaluation_explore.ipynb).
> These results were adversarially audited by a review panel before writing; the
> corrections it forced are folded in (and noted where they matter).
> **Re-run 2026-08-07 on the graph-driven path:** every measured lifecycle now executes
> the real consumer/provider LangGraph graphs (deterministic admission on the catalogue
> ledger, A2A loopback codec, the controller's real FastAPI app through an in-process
> client). The deterministic condition is the *same graphs* with the judgment slots
> swapped for deterministic policies — no more harness shortcut. The adversarial matrix
> grew a fourteenth probe: overselling, rejected at the provider-admission layer.
> **Executable twin:** [`e2e/notebooks/paper.ipynb`](../e2e/notebooks/paper.ipynb)
> recomputes every number here from the raw JSONL and runs a live lifecycle;
> its §5 asserts fail if this file and the data ever drift.

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
  components are **co-located and called in-process** — the A2A hop is the schema-level
  loopback codec (real JSON payloads, no envelope or socket) and the controller's real
  FastAPI app answers through an in-process test client (real routing/validation, no live
  transport) → latencies are a transport-free lower bound; (3) the **datapath carve-out**
  above; (4) **n=20 sequential, single machine, single run, warm** → medians characterize
  typical cost, not tails or throughput; (5) **one LLM** (Qwen3-4B) on **one Modal
  deployment, one session**. No component was mocked — that pairing of a real stack with
  named simulation boundaries is where the credibility comes from.

## 3. Headline result

**Feasible for tokenized network-service provisioning at window/lease timescales.** The
deterministic, security-bearing code this thesis contributes runs in **~90 ms** end to end
— through the real agent graphs — and its authorization decision costs **~125 nanoseconds**;
making provisioning trust-minimized
adds **~69 ms** over a bare device write. The visible cost of an *agent market* is the LLM
round-trips (~4.7 s) and, on a public chain, block confirmation — both **pluggable policy
choices**, not properties of the design. **80/80 lifecycles completed with zero failures.**

## 4. Where the time goes (E1 — latency, n=20 per mode×service)

Phase-timed request→enforced. `activate()` runs the predicate *and* the gNMI Set, so we
split *controller compute* from *actuate*. We report **median with [min, max]**; at n=20 a
"p95" is essentially the max, so we don't cite one (a bug that had made it *exactly* the
max was caught in audit and fixed).

| phase | det/bandwidth | trust domain |
|---|---:|---|
| negotiate: admit + quote + decide | ~1 ms (det) · **4.09 s** (llm: quote 1.90 s + decide 2.14 s) | agents |
| sign (EIP-712 + EIP-191) | ~6 ms | crypto |
| settle (chain, instant-mine) | 33 ms | chain |
| controller compute (+ chain reads, in-process API) | ~25 ms | controller |
| actuate (gNMI → srl1) | 22 ms | network |
| graph + A2A-codec plumbing | ~2 ms | agents |
| **end to end** (det, pooled n=40) | **89 ms** [72–143] | |
| **end to end** (live LLM, n=40) | **4.66 s** [4.02–5.13] | |

Telemetry tracks bandwidth within a few milliseconds per shared phase — the "same machine,
one translator" result (M6.3), quantified. **Both conditions run the same compiled
graphs**: det swaps the two judgment slots for deterministic policies (list price; budget
rule), so the det→llm delta *is* the full cost of the two judgment slots on this model,
and that latency is a property of the model/deployment, not the architecture. Per service
the LLM condition lands at 4.19 s (bandwidth) and 4.86 s (telemetry) — the telemetry
need's longer JSON gives both model calls more prompt to read; judgment sits above the
invariance line by design. End-to-end is the consumer graph's **wall clock** (request →
session active), not a sum of phase medians; the ~2 ms the inner clocks don't account for
is reported as plumbing, not hidden.

**Caveat (audit):** 89 ms is a **transport-free, in-process, instant-mine lower bound** on
the protocol's compute. On a real deployment, add per-hop A2A/HTTP RTT and block time (§6b).

## 5. The authorization predicate costs ~125 nanoseconds (E7 — the sharpest number)

`controller.domain.predicate` is a pure function over an `EntitlementView` — zero I/O
(rule 4), verified by import. Since the 2026-08 fold, the scope check also matches the
*requested action* against the entitlement's service type, so E_SCOPE has exactly one
home. Timed in isolation (200k calls per outcome; E_SCOPE benched as the action/type
mismatch):

| outcome | ns/call | | outcome | ns/call |
|---|---:|---|---|---:|
| **allow** (all 6 checks) | **125** | | E_REVOKED | 63 |
| E_NOT_OWNER | 60 | | E_SCOPE | 90 |
| E_NOT_STARTED | 60 | | E_CONFLICT | 100 |
| E_EXPIRED | 71 | | | |

**Claim it defends:** the security-critical judgment the thesis insists must be
deterministic (rule 1) is *not a bottleneck by many orders of magnitude* — the whole
authorization decision is ~125 ns, versus ~2 s for an LLM slot and tens of ms for chain
and gNMI. This is the strongest data-backed form of "the architecture's own contribution is
free"; it isolates the predicate from the chain-reads and gNMI that `activate_s` bundles.

## 6. The entitlement physically governs the wire (E2 — chain-time enforcement)

ADR-004: chain time is the only clock. Two lags show the entitlement's on-chain state drives the
device (config-committed sense, §2):

- **Revocation lag** — on-chain `revoke` mined → policer gone from srl1, via the *real*
  polling watcher (`chainmcp` `watch_revoked` → `controller` `handle_revoked` → gNMI
  delete): **440 ms median** pooled (n=80), range [169, 668] at poll = 0.5 s.
- **Expiry lag** — chain time passes `end_time` → the ExpiryTimer's tick tears down:
  **75 ms median** [67, 80] (a single synchronous gNMI delete).

**Revocation lag is poll-bounded, not fixed** (E9 sweep — this defuses "your number is just
your polling choice"):

| watcher poll | 0.1 s | 0.25 s | 0.5 s | 1.0 s | 2.0 s |
|---|---:|---:|---:|---:|---:|
| revocation lag (median) | 229 ms | 238 ms | 516 ms | 999 ms | 2005 ms |

The **poll interval sets the lag once it exceeds the machinery's own floor** (516/999/2005
at 0.5/1/2 s); at the shortest polls the median flattens near **~230 ms** — event
detection, one gNMI teardown round-trip, and the harness's 50 ms readback cadence, which
the poll can no longer hide. A *tunable operator SLO knob* (the poll) over a *mostly
architectural minimum* (the floor). On a public chain, add event-visibility delay (block
time) — the same extrapolation caveat as settlement.

**Claim it defends:** revocation and expiry are enforced on real hardware within a bounded,
tunable lag whose floor is one device round-trip — the entitlement is authorization, not
paperwork.

## 7. What it costs (E3 — gas → dollars, per service type)

Execution `gasUsed` measured on a local EVM (Anvil — exact for these contracts at the
pinned solc/hardfork). **Reported per service** because fulfill is bimodal: telemetry offers
carry much larger ABI-encoded params (a pooled median would describe no real transaction).

| op | bandwidth (gas) | telemetry (gas) |
|---|---:|---:|
| fulfill (buyer-paid: mint + settle) | 268,386 [268k–319k] | 447,719 |
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

Fourteen probes drawn from the documented threat model, each run end-to-end on the real
stack and attributed to the layer that rejected it. **Thirteen were rejected at their
designed layer** (3 at the contract, 9 at the controller, 1 at the provider's admission
ledger; predicted layer == actual layer in all 13), and one is allowed by design:

| probe | rejected by | code |
|---|---|---|
| replay a consumed offer (same salt) | contract | `OfferAlreadyUsed` |
| forged provider signature | contract | `BadSignature` |
| fulfill a lapsed offer (`valid_until` past) | contract | `OfferExpired` |
| activate before the window opens | controller | `E_NOT_STARTED` |
| proof signed by a non-owner | controller | `E_NOT_OWNER` |
| garbage activation signature | controller | `E_NOT_OWNER` |
| replay a consumed challenge nonce | controller | `E_NONCE_REUSED` |
| activate the same entitlement twice | controller | `E_CONFLICT` |
| telemetry action on a bandwidth entitlement | controller | `E_SCOPE` |
| activate a revoked entitlement | controller | `E_REVOKED` |
| challenge a nonexistent entitlement | controller | `E_UNKNOWN_ENTITLEMENT` |
| activate after the window ends | controller | `E_EXPIRED` |
| oversell the pool (second sale, full pool) | provider admission | declined; no offer signed |
| second valid entitlement, same resource | — allowed by design | (mints and activates) |

Three layers, independent: the chain rejects bad *money* (forged / replayed / expired
offers) with no controller; the controller rejects bad *access* (owner / nonce / time /
scope / revocation) without trusting the agent; and the provider's admission arithmetic
refuses to oversell before anything exists to sign. Defenses are deterministic code
(rule 1).

**Honest scope (audit):** these are *enumerated tests of known guards written by the
system's author*, not a fuzzing or economic adversary. Rejection is raised **upstream of any
gNMI call** in the code path — so no rejected probe configured the device — but this is an
architectural property of where the checks sit, not a per-probe device readback. **Untested
attack classes** (named as future work): input fuzzing, chain-level adversaries
(front-running fulfill, a reorg racing the revocation watcher), and malformed-parameter
translation. The allowed case and the oversell probe are two halves of one placement: a
*second valid entitlement on the same resource* activates and **does** configure the
device — per-resource capacity is the provider's `CapacityLedger` concern at quote time,
not a controller security check (`E_CONFLICT` is strictly per-entitlement) — while the
oversell probe drives that ledger directly and shows it refusing a second sale against a
pool with room for exactly one. Rights at the controller, inventory at the provider,
measured on both sides.

## 9. The price of trustlessness (E6 — baseline)

The same 50 Mbps path provisioned with **no agents, no chain, no controller** — one direct
`netctl` call — takes **20 ms**. The full deterministic lifecycle takes 89 ms. So trust-
minimization adds **~69 ms**, which decomposes as: on-chain settle ~33 ms (instant-mine
lower bound) + signing (offer + proof) ~6 ms + challenge + controller compute + chain reads
+ in-process API dispatch ~25 ms + graph/codec plumbing ~2 ms. **The authorization
predicate itself is ~0.1 µs** (§5) — the security *logic* is
free; the ~69 ms is settlement, signatures, and the controller's own chain reads, most of
which is the (here-instant) chain write.

## 10. The judgment layer (E5 — LLM), reported precisely

Two slots against the deployed Qwen3-4B, one session, through the provider graph's own
prompt (one source of truth since the 2026-08 unification: a neutral system prompt, the
list price passed as data):

- **Quote** (Bell prices): **10/10 schema-valid, first attempt, 0 retries**, all in the
  [5,25] TOK band. But **every quote was exactly 15 TOK** across needs spanning 10–500 Mbps
  — the *midpoint of the permitted band*, not the 10-TOK list price supplied in the
  prompt. The slot shows **no sensitivity to requested capacity or to the stated list
  price**: it anchors on the prompt's band. So this validates **schema + constraint
  compliance**, not price discovery; any "prices vary" claim would be false on this data.
  (Under the pre-unification prompt, which named the list price in the system message, the
  same model anchored at 10 TOK — the anchor follows the prompt framing, which is itself
  the finding.) (~2.05 s, ~277 tokens/call.)
- **Decide** (Ada accept/reject, graded vs ground-truth *accept-iff-affordable*): **12/12
  correct** (9/9 excluding the 3 `price==budget` boundary cases, whose accept-at-equality
  convention is a prompt choice). This is a **curated smoke test of a one-comparison
  function**, single sample per case — it shows the model handles clean threshold decisions
  and the validate-and-retry guard returns a valid object or a safe *decline*, never a
  hallucinated shape. It is **not** a robustness benchmark (no malformed offers, no repeated
  sampling). (~1.98 s, ~838 tokens/call.) Note the judged lifecycles rode this convention
  end to end: every negotiated price was 15 TOK against a 15-TOK budget, so
  accept-at-equality carried all 40 runs.
- **Cost per negotiation:** quote + decide ≈ **1115 tokens** → **\$0.0002–0.002** at
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
| in-process, co-located components | 89 ms excludes live A2A/HTTP hops: the A2A leg is the loopback codec, the controller API an in-process ASGI client; a transport-free lower bound on real code |
| ADR-006 datapath carve-out | "enforced" = config committed + read back, not packets shaped; datapath proof is the separate console iperf plateau |
| adversarial = enumerated own-threat-model tests | every documented guard fires at its layer; fuzzing / reorg / economic adversaries untested |
| LLM = one model, one session, single-sample | latency/accuracy attributed to this deployment; quote pricing is band-anchoring, not discovery |
| gas on Anvil | execution gas exact for pinned solc; L2 user-fee adds an unmeasured L1 data-fee component |

## 12. Conclusions

The evaluation supports a **bounded** feasibility claim:

1. A trust-minimized provisioning completes in **89 ms** (deterministic) / **4.7 s** (live
   LLM), request → enforced (config-committed) on a real router, **through the real agent
   graphs in both conditions**; **80/80 runs, 0 failures.**
2. The **authorization predicate costs ~125 ns**; trust-minimization adds **~69 ms** over a
   bare device write (settle + signatures + chain reads) — the security logic is free.
3. On-chain revocation is enforced in **~440 ms** at a 0.5 s watcher poll, **tracking the
   poll wherever it exceeds the ~230 ms floor** (a tunable SLO knob over a mostly
   architectural minimum) — the entitlement governs the wire.
4. **13/14 threat-model probes rejected** at their designed layer (3 contract / 9
   controller / 1 provider admission), upstream of any device write; the one allowed case
   documents, and the oversell probe demonstrates, capacity's placement at quote time.
5. A provisioning costs **268k gas** (bandwidth) / **448k** (telemetry) — a few cents on an
   L2, \$6–40 on L1 — feasible on any rollup.
6. LLM decisions are **12/12 correct** on curated cases with a fail-safe guard, at **~1115
   tokens (<1¢) per negotiation** — an agent market is viable.

**Boundaries, stated plainly:** feasible for provisioning at minute timescales, **not**
real-time per-flow setup on L1; enforcement measured as config-on-device (ADR-006; the
console iperf plateau is the datapath proof); chain latency and L1 fees extrapolated, not
measured; n=20 single-machine (no throughput/tail claims); adversarial coverage limited to
the documented threat model; LLM pricing not demonstrated. Within those bounds, the
architecture does what the thesis claims — and the deterministic, trust-critical core it
contributes is, by orders of magnitude, not the thing that costs anything.

## 13. Reproduce

```sh
containerlab deploy -t netlab/topology.clab.yml           # the router
set -a && source .env && set +a                           # for --mode llm (deployed model)
uv run python -m e2e.experiments --exp all --n 20         # latency+expiry+baseline+adversarial+llm
uv run python -m e2e.experiments --exp predicate          # E7 (no lab/chain needed)
uv run python -m e2e.experiments --exp revlag_sweep       # E9 (lab; ~6 min)
uv run --group demo jupyter nbconvert --to notebook \
  --execute --inplace e2e/notebooks/evaluation_explore.ipynb   # the figures + tables
```

Deterministic-only (faster, no `.env`): `--mode det`. Data: `e2e/runs/eval/*.jsonl`
(committed as evidence). Contract-gas cross-check: `cd contracts && forge snapshot`.
