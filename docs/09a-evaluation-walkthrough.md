# 09a — The evaluation, explained from zero

> **Who this is for.** Someone who has read `docs/00-the-story.md` (or at least the
> prologue: Ada buys 50 Mbps from Bell for 10 TOK, gets ticket #7, and a real router
> obeys) and now wants to understand *how we know the design is any good* — without
> assuming they have ever benchmarked anything, read a gas table, or heard the word
> "median" used in anger. Every term is glossed where it first appears.
>
> **How this fits the docs.** This is the narrative twin of
> [`docs/09-evaluation.md`](09-evaluation.md), the formal report. The report states
> results compactly for an examiner; this walkthrough builds each one up from the
> problem it answers. Same numbers, same source: the harness in
> `e2e/src/e2e/experiments.py`, raw data in `e2e/runs/eval/*.jsonl`, figures in
> [`e2e/notebooks/evaluation_explore.ipynb`](../e2e/notebooks/evaluation_explore.ipynb).

**The one-sentence answer you came for:** we ran seven measured experiments against the
*real* running system — real chain, real controller, real router, real LLM — and they
show the architecture is feasible for provisioning network services at minute timescales:
the trust machinery this project contributes costs ~90 milliseconds end to end, its core
security decision costs ~90 *nanoseconds*, every attack from the threat model was
rejected, and the visible costs (LLM seconds, chain fees) belong to swappable parts, not
to the design.

---

## Chapter 1 — why "it works" is not enough

By the end of milestone M6.5 the demo works. You can watch it live: Ada asks Bell for
50 Mbps, Bell quotes 10 TOK, Ada pays, ticket #7 is minted, the controller checks the
ticket and configures the router `srl1`, and an `iperf` traffic test visibly plateaus at
~49 Mbps. Every piece is real. So — done?

No, and the reason is the difference between an **existence proof** and an
**evaluation**. The demo proves the architecture *can be built*: at least one run, on at
least one machine, once, succeeded. That answers exactly one question. A skeptical
examiner — or a future operator deciding whether to build on this — has different
questions, and the demo answers none of them:

- **How fast is it?** "It worked" could mean 90 milliseconds or 90 seconds. Which?
- **Where does the time go?** If it's slow, is the *design* slow, or is one replaceable
  part slow?
- **What does it cost?** Every purchase writes to a blockchain, and blockchain writes
  cost real money. Cents or dollars?
- **Can it be cheated?** The whole point is that strangers who distrust each other can
  trade. That claim is empty until someone *tries* to cheat and fails.
- **Does revocation actually work?** A ticket you can't take back isn't authorization,
  it's paperwork.
- **Is the AI part reliable enough?** LLMs are famous for making things up. Two of them
  sit in the buying loop.
- **How often does it fail?** Once is an anecdote.

Each question needs a *number*, and each number needs an experiment designed to produce
it. That is what an evaluation is: turning "it works" into "it works this fast, at this
cost, within these limits — and here is where the limits are." The limits matter as much
as the successes; a report that hides them is advertising, not evidence.

Seven experiments, named E1–E7 plus a sweep called E9, provide the numbers. The rest of
this document walks through them in a teaching order (not numeric order): first *how we
measured*, then *time*, then *money*, then *security*, then *judgment*, then the part
where the evaluation itself got audited.

---

## Chapter 2 — honesty first: pin the words down before any number

A dishonest evaluation doesn't usually lie with numbers; it lies with *words*. "Enforced"
can mean many things. "Real" can mean many things. So before a single measurement, the
report fixes two definitions, and every claim afterwards inherits them. This walkthrough
needs them too.

### 2.1 What "enforced on the device" means here

When we say a purchase was "enforced", we mean: the configuration that implements it —
a **policer** (a rule in the router that caps traffic to a rate, here 50 Mbps) for
bandwidth, or an export destination for telemetry — was **written into the real router
`srl1` via gNMI and then read back from the router's running configuration**. Two glosses:

- **gNMI** — a standard management protocol (a wire format + verbs like Set and Get) that
  network devices expose so software can configure them, instead of a human typing into a
  console. `netctl` speaks it.
- **running configuration** — the live state the router is *currently obeying*, as
  opposed to something we merely sent and hoped arrived. Reading it back closes the loop:
  the router itself confirms the policer exists.

What "enforced" does **not** mean here: that we watched packets being rate-limited in the
same breath as the measurement. The router in the lab is **containerized SR Linux** — a
real router operating system running as a container — and in container form its
**datapath** (the part that actually forwards packets) does not apply QoS rate limits,
a known limitation recorded in **ADR-006**. The proof that the *concept* reaches packets
exists separately: the live `just console` demo, where an iperf test drops from
~100 Mbps to ~49 Mbps the moment the policer lands. The evaluation measures
config-committed-and-read-back; the console demo shows physics. Keeping those two claims
separate — instead of blurring them into one — is the first honesty decision.

### 2.2 What is real and what is simulated

The stack under test is real in the sense that **no component was replaced by a mock**
(a stand-in that fakes behavior): the actual smart contract on an actual EVM chain, the
actual controller code, actual gNMI writes to an actual SR Linux container, the actual
Qwen3-4B model deployed on Modal answering actual prompts. But five things about the
*test conditions* are simplified, and each one caps a specific claim:

1. **The chain is Anvil, and Anvil mines instantly.** Anvil is a local development
   blockchain. On a public chain, a transaction waits for the next **block** (the batch
   of transactions the network periodically confirms) — seconds to minutes. Anvil skips
   the wait. Consequence: every chain latency we measure is a **lower bound** — the
   true value on a public chain is *at least* this, plus block time. (A lower bound is
   still informative: it isolates the compute cost from the consensus cost.)
2. **Everything runs on one machine, calling each other in-process.** In production,
   Ada, Bell, and the controller would talk over the network (A2A protocol over HTTP),
   adding round-trip time per hop. Our timings exclude that: a *transport-free* lower
   bound.
3. **The datapath carve-out** from §2.1.
4. **n=20, sequential, one machine, one run, warm.** "n=20" means each measurement was
   repeated 20 times; "sequential" means one at a time, never concurrently; "warm" means
   after everything was already loaded and connected (no cold-start costs included). This
   supports claims about *typical per-lifecycle cost*, and nothing about throughput (how
   many per second the system could sustain) or tail behavior (the rare slow cases).
5. **One LLM, one deployment, one session.** Every LLM number describes Qwen3-4B on that
   day's Modal deployment, not "LLMs".

Memorize the shape of this list rather than its contents: *each simplification is named,
and each names the claim it weakens.* That pairing — a fully real stack plus explicitly
drawn boundaries — is where the evaluation's credibility comes from. An evaluation that
claims more than its setup can support is worthless; one that claims less than it proved
is timid; the skill is claiming exactly what the setup supports.

---

## Chapter 3 — the measuring apparatus

All seven experiments live in one file: `e2e/src/e2e/experiments.py`. Its anatomy:

- A `Stack` (`experiments.py:105`) assembles the real components — chain client,
  controller, gNMI provisioner — exactly as the demo wires them, minus any dashboard.
- `run_lifecycle` (`experiments.py:205`) executes one complete purchase — negotiate →
  sign → settle → activate → enforce — with a stopwatch around each phase, and returns a
  dict of phase timings. This one function is the heart of the latency experiments.
- One `exp_*` function per experiment (`exp_latency` at `experiments.py:307`,
  `exp_predicate` at `:610`, `exp_adversarial` at `:393`, and so on), each writing its
  raw rows to `e2e/runs/eval/*.jsonl`.
- **JSONL** — a file with one JSON object per line; the simplest format that lets every
  individual measurement be kept, inspected, and re-analyzed later. The raw files are
  committed to the repo as evidence, so anyone can recompute the summary statistics
  instead of trusting them.
- The notebook `evaluation_explore.ipynb` reads those files and renders the figures —
  it computes nothing new, so the figures can't silently disagree with the data.

Two statistics vocabulary items, because every table below uses them:

- **Median** — sort the 20 measurements, take the middle one. We report medians rather
  than averages because a single freak-slow run (the OS deciding to do something else
  for 40 ms) drags an average but barely moves a median. The median answers "what does a
  *typical* run cost?", which is the question feasibility asks.
- **[min, max]** — the fastest and slowest observed, in brackets, so the spread is
  visible next to the typical value.
- What we deliberately do **not** report: a **p95** (the value 95 % of runs beat).
  With only 20 samples, "p95" is arithmetically just the 19th-of-20 value — essentially
  the maximum wearing a lab coat. An early draft *did* report one; the audit
  (chapter 10) caught that it was literally the sample max, and it was removed. Small
  samples earn medians and ranges, nothing fancier.

---

## Chapter 4 — E1: where the time goes

**The question:** when Ada clicks "buy" (so to speak), what happens to the clock between
that moment and the policer existing on `srl1`?

**The idea:** don't measure one total; measure each *phase*, because the phases belong to
different trust domains, and feasibility verdicts differ per domain. A slow LLM is a
model choice; a slow controller would be an architecture flaw. One total number can't
tell those apart; a phase breakdown can.

The lifecycle decomposes into five timed phases:

1. **negotiate** — Ada asks, Bell quotes, Ada decides. This is where the two LLM calls
   live (and the *only* place: hard rule 1).
2. **sign** — Bell signs the offer (EIP-712, a standard for signing structured data so
   the contract can verify exactly what was agreed) and Ada signs her activation proof
   (EIP-191, a simpler message-signing standard). Pure cryptography, no network.
3. **settle** — the `fulfill` transaction on the chain: atomically move 10 TOK from Ada
   to Bell and mint ticket #7 to Ada. ("Atomically": both happen or neither does — the
   fair-exchange answer from story chapter 2.)
4. **controller compute** — the controller verifies Ada's proof, reads the ticket's
   on-chain state, and runs the authorization predicate (the checks from story
   chapter 5). Includes its chain *reads*.
5. **actuate** — `netctl` writes the policer to `srl1` via gNMI Set.

The experiment runs 20 lifecycles per combination of mode (deterministic vs live-LLM —
next paragraph) and service (bandwidth vs telemetry): 80 lifecycles total. **All 80
completed; zero failures.** That is the reliability anecdote-killer from chapter 1:
still a small n, but "80/80" is a very different sentence than "it worked when we tried
it."

**The two modes.** In `llm` mode, negotiation really calls the deployed Qwen3-4B twice
(Bell's quote, Ada's decision). In `det` (deterministic) mode, negotiation is skipped
entirely and the canonical fixed price is used — not because a deterministic negotiator
exists in production (it doesn't; the production consumer always calls the LLM), but as
an experimental *control*: with judgment removed, whatever time remains is the pure
mechanical cost of the trust machinery.

**The result** (medians; full table in [`docs/09`](09-evaluation.md) §4):

| phase | time | trust domain |
|---|---:|---|
| negotiate | 0 (det) · 3.05 s (llm) | agents (LLM) |
| sign | ~6 ms | cryptography |
| settle | 38 ms | chain (instant-mine) |
| controller compute | ~23 ms | controller |
| actuate | 21 ms | network device |
| **end to end, det** | **89 ms** [68–129] | |
| **end to end, llm** | **3.27 s** [3.10–3.62] | |

Read it in three passes:

- **The deterministic machinery — everything this thesis actually contributes — is
  89 milliseconds**, request to policer-on-router. For scale: a human eye-blink is
  ~150 ms. And that 89 ms is dominated by three unavoidable I/O acts — one chain write,
  chain reads, one router write — each in the tens of milliseconds.
- **The LLM mode is 3.27 s, of which ~3.05 s (~96 %) is the two LLM calls.** In the E1
  figure (`docs/evidence/assets/m7.1-latency-by-phase.png`) this is the purple bar
  that dwarfs everything: the picture *is* the finding. The delta between modes is
  entirely the judgment layer, and judgment latency is a property of which model you
  deploy where — swap the model, the number moves; the architecture doesn't.
- **Telemetry tracks bandwidth within a millisecond per phase.** The second service
  (story chapter 7) rides the same machinery at the same cost — the "one translator
  added, nothing else changed" claim of M6.3, now quantified.

**The caveat, inherited from chapter 2:** 89 ms is a transport-free, instant-mine lower
bound. A real deployment adds network hops between agents and block time on the chain
(chapter 8 extrapolates the latter). The honest sentence is: *the protocol's compute
costs ~90 ms; everything above that is transport and consensus, priced separately.*

---

## Chapter 5 — E7: the ninety-nanosecond bouncer

**The question:** hard rule 1 insists the authorization decision — may this ticket
configure this router now? — must be deterministic code, never an LLM. A skeptic flips
that into an attack: *fine, but what does your deterministic purity cost?* If the
predicate were expensive, "no LLM in the loop" would be a tax.

**Why E1 can't answer it:** in E1, the controller's ~23 ms bundles chain reads, proof
verification, and the predicate together. To price the predicate *itself*, it must be
measured in isolation.

**Why isolation is even possible** — and this is the pretty part — is hard rule 4: the
predicate (`controller/src/controller/domain.py:20`) is a **pure function**. Glosses:

- **Pure function** — a function whose output depends only on its inputs: no network, no
  disk, no clock, no hidden state. Same inputs, same answer, forever.
- The predicate takes an `EntitlementView` — a plain snapshot of the ticket's state
  (owner, window, scope, revoked-flag) that *someone else* already fetched from the
  chain — and returns allow, or a typed denial code. The architecture forced the I/O to
  the edges precisely so the decision would be this: a closed-form check over a struct.

A pure function can be benchmarked the way physicists like: call it 200,000 times in a
tight loop (`exp_predicate`, `experiments.py:610`, using Python's `timeit`), divide.
Once per possible outcome:

| outcome | ns/call | | outcome | ns/call |
|---|---:|---|---|---:|
| **allow** (all 6 checks pass) | **86** | | E_REVOKED | 70 |
| E_NOT_OWNER | 51 | | E_SCOPE | 79 |
| E_NOT_STARTED | 56 | | E_CONFLICT | 83 |
| E_EXPIRED | 65 | | | |

A **nanosecond** is a billionth of a second; 86 ns is the time light travels about 26
meters. Two readings:

- **The full allow path — all six security checks — costs 86 nanoseconds.** Against the
  ~1.6 s of a single LLM call, that is a factor of about twenty million. The
  security-critical judgment the thesis insists on making boring is, by seven orders of
  magnitude against the LLM and three against everything else, *not the bottleneck*.
  This is the sharpest number in the evaluation, and the strongest data-backed form of
  "the architecture's own contribution is free."
- **Every denial is cheaper than allow, and the bar order mirrors the documented check
  order.** The predicate checks ownership first (51 ns to deny), then window-start, then
  expiry, and so on; a denial exits at its check. The microbenchmark accidentally
  *re-documents the code's structure* — a nice sanity signal that we measured the real
  thing.

---

## Chapter 6 — E2 and E9: the ticket governs the wire

**The question:** minting ticket #7 turned money into authorization. But authorization
you cannot *withdraw* is just a receipt. If Bell revokes the ticket on-chain (story
chapter 6 — refund-and-revoke), does the policer actually leave the router? How fast?
And when the window simply expires at 16:00, does the configuration come down by itself?

This is ADR-004 territory: **chain time is the only clock**. The router has no idea
tickets exist; some component must notice the chain changed and act. Two mechanisms, two
measurements.

### 6.1 Revocation lag (E2)

The real production pipeline — not a shortcut built for the test — is: `chainmcp` runs a
**watcher** that **polls** the chain (asks it at a fixed interval: "any `Revoked` events
since I last looked?"), and on a hit calls the controller's `handle_revoked`, which
tears the policer down via a gNMI delete. The measurement: timestamp when the `revoke`
transaction is mined, timestamp when the policer is gone from `srl1`'s running config
(read back, per the chapter 2 definition), report the difference.

**Result: 464 ms median** (n=80 pooled, range [237, 647]) at the default poll interval
of 0.5 s.

A skeptic should immediately object: *that number is just your polling choice.* At a
0.5 s poll, a revocation waits on average a quarter-second just to be *noticed* —
so is 464 ms measuring the architecture or the config file? The objection is correct,
and experiment **E9** (`exp_revlag_sweep`, `experiments.py:644`) exists to absorb it:
rerun revocation at five poll intervals.

| watcher poll | 0.1 s | 0.25 s | 0.5 s | 1.0 s | 2.0 s |
|---|---:|---:|---:|---:|---:|
| revocation lag (median) | 182 ms | 248 ms | 508 ms | 990 ms | 1999 ms |

The pattern is exact: **lag ≈ poll interval + ~80 ms**. That decomposition is the
finding. The poll term is an *operator knob* — a service-level choice trading chain-query
load against reaction speed, tunable at will. The ~80 ms floor is the *architectural
minimum*: detection plus one gNMI round-trip to delete the policer. On a public chain a
third term appears — the block time before the revocation event is even visible — which
belongs to the chain choice, same as settlement (chapter 8).

### 6.2 Expiry lag

Expiry needs no watcher: the controller's ExpiryTimer schedules a wake-up for the
ticket's `end_time`, and — per ADR-004 — the woken code *re-checks chain time* before
acting (OS timers may drift or fire early; the chain is the authority). The measured
tick-to-deconfigured lag: **73 ms median** [65, 85] — one synchronous gNMI delete,
consistent with the ~80 ms actuation floor seen from the other direction in E9.

**The claim both defend:** the on-chain ticket doesn't just *permit* configuration — its
state change *removes* configuration, on real hardware, within a bounded lag whose floor
is one device round-trip. The entitlement is authorization, not paperwork.

---

## Chapter 7 — E6: the price of trustlessness

**The question:** all this machinery — signatures, a chain, a controller — exists so
that *strangers* can trade. An operator who already trusts its buyer needs none of it: it
would just configure the router. What premium does trustlessness charge?

**The idea:** measure the **baseline** — the same 50 Mbps policer on the same router via
one direct `netctl` call, no agents, no chain, no controller (`exp_baseline`,
`experiments.py:369`) — and subtract.

- Bare device write: **20 ms**.
- Full deterministic lifecycle (E1): **89 ms**.
- **Trust-minimization premium: ~69 ms**, decomposing as: on-chain settle ~38 ms
  (instant-mine lower bound) + both signatures ~6 ms + challenge, controller compute,
  and its chain reads ~23 ms.

The connecting insight, with chapter 5 in hand: the predicate — the security *logic* —
is <0.1 µs of that 69 ms, i.e. effectively none of it. The premium is settlement,
signatures, and chain reads: the unavoidable I/O of *recording the trade somewhere
neither party controls*. You pay for the notary, not for the judgment.

---

## Chapter 8 — E3: what a purchase costs in money

**The question:** every `fulfill` is a blockchain transaction, and public blockchains
charge fees. If minting ticket #7 cost $30, no one prices a 2-hour bandwidth window
at 10 TOK. Is the economics survivable?

Glosses first, because this chapter is jargon-dense:

- **Gas** — the chain's unit of computational work. Every transaction consumes a
  measurable amount of gas; `fulfill` (verify Bell's signature, move 10 TOK, mint
  ticket #7, record the sale) consumes more than a plain money transfer because it does
  more work.
- **Gas price** — what one unit of gas costs in ETH at the moment you transact, quoted
  in **gwei** (a billionth of an ETH). It floats with demand. Your fee =
  gas used × gas price.
- **L1 / L2** — Ethereum proper is "layer 1"; **rollups** ("layer 2") are chains that
  execute cheaply off to the side and post compressed evidence back to L1, giving
  L1-backed security at a small fraction of the fee.

**The mechanism:** gas *used* is deterministic — it depends on the contract code and
inputs, not on network mood — so measuring it on local Anvil with the pinned compiler
gives the exact figure a public chain would charge for execution. The harness reads
`gasUsed` from each transaction receipt (`experiments.py:198`):

| operation | bandwidth (gas) | telemetry (gas) |
|---|---:|---:|
| `fulfill` (buyer pays: settle + mint) | 268,050 | 447,371 |
| `revoke` (issuer pays) | 29,903 | 29,903 |
| `approve` (one-time token setup) | 46,366 | 46,366 |

Two methodological points worth internalizing:

- **Why per-service, not pooled.** Telemetry offers carry much larger ABI-encoded
  parameters (the byte-serialized arguments stored with the sale), so `fulfill` gas is
  **bimodal** — two distinct clusters, 268k and 447k, with nothing in between. An early
  draft pooled all fulfills into one median (383k) — a number describing *no real
  transaction*. The audit killed it. When data is bimodal, report the modes.
- **The independent cross-check.** `forge snapshot` — Foundry's own gas reporter,
  running over the contract test suite, sharing no code with our harness — reports
  fulfill at 324–347k (different offer fixtures, different storage warmth). Same order
  of magnitude, mechanism understood for the difference. Two disagreeing-in-detail,
  agreeing-in-magnitude instruments beat one instrument.

**Cashing gas out in dollars** (ETH at $3,000, illustrative mid-2026 prices; on an L2
add an unmeasured L1 data-fee for posting the calldata):

| | L2 @ 0.03 gwei | L1 @ 8 gwei | L1 @ 30 gwei |
|---|---:|---:|---:|
| bandwidth fulfill | ~$0.024 | ~$6.40 | ~$24 |
| telemetry fulfill | ~$0.040 | ~$10.70 | ~$40 |

**The reading:** on any rollup, a provisioning costs *a few cents* — negligible against
any plausible service price. On Ethereum L1 it costs $6–40, which doesn't kill the
design but *shapes the product*: on L1 you'd lease longer windows to amortize the fee,
never price per-flow. A feasibility **boundary**, located and stated — which is exactly
what an evaluation is for — not a failure.

### 8.1 And chain *latency*, extrapolated

Anvil's instant mining hid one cost that must be priced analytically (calculated from
known block times, not measured — the report says so in ink):

| chain | settle wait | full det provisioning |
|---|---|---|
| Anvil (measured) | instant | ~0.09 s |
| L2 rollup (~1 block) | ~2 s | ~2.1 s |
| Ethereum L1 (1 confirmation) | ~12 s | ~12 s |
| Ethereum L1 (full finality) | ~13 min | ~13 min |

The verdict this table supports: feasible at *provisioning* timescales — Ada booking a
14:00–16:00 window at 13:30 doesn't care about 2 s, or even 12 s — and plainly unfit
for real-time per-flow admission on L1. Both halves of that sentence are findings.

---

## Chapter 9 — E4: trying to cheat

**The question:** the design's central promise is that neither stranger can rob the
other, and no third party can hijack the router. Chapters 4–8 measured the honest path.
This chapter attacks it.

**The method:** the project's threat model (the documented list of ways a malicious
party could try to subvert the system) yields twelve concrete attacks. Each is executed
**end-to-end against the real stack** (`exp_adversarial`, `experiments.py:393`) — a real
malicious transaction to the real contract, a real forged request to the real
controller — and for each we record not just *that* it failed but **which layer rejected
it, compared against which layer the design says should**. Defense location is part of
the design; verifying it is part of the test.

**Result: 12/12 rejected, every one at its predicted layer** — 3 at the contract, 9 at
the controller:

| attack | rejected by | error |
|---|---|---|
| replay an already-consumed offer (same salt) | contract | `OfferAlreadyUsed` |
| forge Bell's signature on an offer | contract | `BadSignature` |
| fulfill an offer past its `valid_until` | contract | `OfferExpired` |
| activate before the window opens | controller | `E_NOT_STARTED` |
| activation proof signed by a non-owner | controller | `E_NOT_OWNER` |
| garbage bytes as the activation signature | controller | `E_NOT_OWNER` |
| replay a consumed challenge nonce | controller | `E_NONCE_REUSED` |
| activate the same ticket twice | controller | `E_CONFLICT` |
| telemetry action on a bandwidth ticket | controller | `E_SCOPE` |
| activate a revoked ticket | controller | `E_REVOKED` |
| challenge a ticket that doesn't exist | controller | `E_UNKNOWN_ENTITLEMENT` |
| activate after the window ends | controller | `E_EXPIRED` |

The split is the architecture made visible: the **contract rejects bad money** (forged,
replayed, lapsed offers) with the controller nowhere in the loop, and the **controller
rejects bad access** (wrong owner, reused nonce, wrong time, wrong scope, revoked)
without extending the agent an ounce of trust. Two independent walls; a cheat must beat
both. And every rejection is deterministic code — hard rule 1 holds under attack, not
just in prose.

One structural note: every rejection fires *upstream of any gNMI call* in the code path,
so no rejected attack touched the router. The report is careful about the epistemic
status of that sentence — it's an architectural property of where the checks sit
(verified by reading the code path), not a per-attack device readback.

**Now the honest scope, because this is where evaluations most often oversell.** These
twelve are *enumerated tests of documented guards, written by the system's own author*.
They prove every guard fires where designed. They do **not** prove no thirteenth attack
exists — the author probing their own threat model cannot, by construction, discover
threats outside their imagination. Untested and named as future work: **fuzzing**
(bombarding inputs with random malformations to find crashes no one thought of),
chain-level adversaries (**front-running** — seeing your pending transaction and racing
one in ahead of it; a **reorg** — the chain briefly rewriting recent history — racing
the revocation watcher), and malformed-parameter translation.

And one case is **allowed by design**, kept in the report so no one mistakes it for a
hole: a *second valid ticket on the same resource* activates and does configure the
device. Overselling capacity is prevented at quote time by the provider's
`CapacityLedger` (Bell's own bookkeeping; tested in M5.2) — an economic concern owned
by the party bearing the economic risk — not by the controller, whose `E_CONFLICT` is
strictly per-ticket. Knowing *which layer owns which guarantee* is the difference
between a security argument and a security vibe.

---

## Chapter 10 — E5: the judgment layer, graded

**The question:** exactly two decisions in the whole system belong to an LLM (hard
rule 1): Bell's *quote* (what price?) and Ada's *decide* (accept or reject?). LLMs
produce plausible text, which is not the same as correct decisions. Is the judgment
layer reliable enough, and what does it cost per negotiation?

**Slot 1 — Bell's quote**, 10 trials across needs from 10 to 500 Mbps. The mechanical
result is clean: **10/10 structurally valid on the first attempt** (the reply parsed
into the required schema — the exact expected shape with the exact expected fields —
with zero retries), and every price inside the instructed [5, 25] TOK band. The model
obeys structure and constraints.

Then the finding an unscrupulous report would have buried: **every single quote was
exactly 10 TOK** — the list price stated in the prompt — across a 50× range of
requested capacity. The model **anchored** (latched onto the salient number in its
context and echoed it) and exhibited *zero capacity-dependent pricing*. So this data
validates schema-and-constraint compliance and nothing more; any sentence shaped like
"the provider prices dynamically" would be false on this evidence. The evaluation says
so in those words. (~1.45 s and ~276 tokens per call — a **token** being the roughly
word-sized chunk LLM usage is billed in.)

**Slot 2 — Ada's decision**, 12 cases graded against **ground truth** (the objectively
correct answer, computable here because the policy is *accept iff price ≤ budget*):
**12/12 correct** — 9/9 on the clear cases, plus 3 `price == budget` boundary cases
whose accept-at-equality convention is set by the prompt, so the report scores them
separately rather than claiming them as model brilliance. Equally important: the
validate-and-retry guard around the slot either returns a schema-valid object or a safe
*decline* — a malformed LLM reply can waste a purchase, never corrupt one. The report
names this what it is: a **curated smoke test of a one-comparison function** — single
sample per case, no malformed offers, no repeated sampling — not a robustness benchmark.

**The cost:** quote + decide ≈ **1,114 tokens ≈ $0.0002–0.002** per complete
negotiation at typical per-token prices. Judgment overhead is a rounding error against
any service price.

**The claim, at its honest size:** the agent-market layer is viable — decisions are
correct on unambiguous cases, failures are safe, and negotiation costs a fraction of a
cent. Pricing *judgment* was not demonstrated (one model, one session), and the report's
credibility rests partly on having said so unprompted.

---

## Chapter 11 — the evaluation of the evaluation

The step that most distinguishes this evaluation from a demo with tables: **before the
report was written, the draft summary was adversarially audited by a four-agent review
panel** — independent reviewers instructed to attack the claims, not admire them. The
kills, each already mentioned in its chapter, collected:

1. **The fake p95** (chapter 3): at n=20, `int(0.95 · 20) = 19` — the reported "p95"
   was literally the sample maximum. Removed; medians and ranges only.
2. **The pooled gas median** (chapter 8): 383k described no real transaction; the data
   is bimodal by service type. Re-reported per service.
3. **An inflated expiry lag**: the measurement accidentally included a full extra gNMI
   readback inside the timed window. Fixed.
4. **A late-anchored revocation clock**: the timer started after an extra receipt RPC,
   flattering the lag. Re-anchored at mining time.
5. **Four claim-level overclaims** rewritten to what the data supports, among them
   "no attack reached the router" (true, but architecturally — not verified per-attack;
   chapter 9's careful phrasing) and "prices vary" (false; the anchoring finding,
   chapter 10).

The general lesson, worth exporting from this project: **the same adversarial stance the
system applies to agents, the evaluation must apply to itself.** Every one of those five
was the flattering error, never the unflattering one — that is what motivated reasoning
looks like in a benchmark, and why un-audited self-evaluation trends optimistic. The
corrections are folded into `docs/09` §2 and §11, and the audit itself is recorded in
[`docs/evidence/M7.1.md`](evidence/M7.1.md).

---

## Chapter 12 — the verdict, at its honest size

Assemble the chapters into the one paragraph the thesis gets to claim:

**Feasible, for tokenized network-service provisioning at window/lease timescales.**
The deterministic, security-bearing machinery this project contributes completes a
provisioning in **~89 ms** (request → config enforced on a real router; 80/80 runs,
zero failures); its authorization decision costs **~86 ns**; trust-minimization adds
**~69 ms** over a bare device write, essentially all of it settlement and chain I/O.
On-chain revocation reaches the wire in **~464 ms** at a 0.5 s poll, scaling as
poll + ~80 ms floor. All **12/12** threat-model attacks were rejected at their designed
layer. A purchase costs **cents on an L2** ($6–40 on L1, which shapes product design
toward longer leases). The LLM layer decides correctly on clean cases, fails safe, and
costs **under a cent** per negotiation. The two visibly expensive components — LLM
seconds and chain confirmation — are both **pluggable policy choices** (swap the model;
choose the chain), not properties of the architecture.

And the boundary lines, in the same breath: latencies are transport-free, instant-mine
lower bounds; "enforced" means config-committed-and-read-back (ADR-006 — the console
iperf plateau is the datapath proof); no throughput, concurrency, or tail claims (n=20,
sequential, warm); adversarial coverage is the documented threat model, not fuzzing or
chain-level adversaries; LLM results are one model, one session, and pricing judgment
was not demonstrated.

If you retain a single sentence: *the parts this thesis is responsible for are, by three
orders of magnitude, not the parts that cost anything.*

---

## Chapter 13 — run it yourself

Every number above regenerates from scratch (the lab, the chain, and — for LLM mode —
the deployed model must be up; `docs/09` §13 is the authoritative version):

```sh
containerlab deploy -t netlab/topology.clab.yml            # the router
set -a && source .env && set +a                            # creds for --mode llm
uv run python -m e2e.experiments --exp all --n 20          # E1–E6 + LLM
uv run python -m e2e.experiments --exp predicate           # E7 (needs nothing else)
uv run python -m e2e.experiments --exp revlag_sweep        # E9 (~15 min)
uv run --group demo jupyter nbconvert --to notebook \
  --execute --inplace e2e/notebooks/evaluation_explore.ipynb   # figures
```

Deterministic-only (no `.env`, faster): add `--mode det`. Raw data lands in
`e2e/runs/eval/*.jsonl`; the committed copies are the evidence behind `docs/09`. The
independent gas cross-check: `cd contracts && forge snapshot`.

---

**Check question** (answer out loud before moving on): E1 says a deterministic lifecycle
takes 89 ms and E7 says the predicate takes 86 ns — a difference of six orders of
magnitude. Where do the missing ~89 ms live, and why does that decomposition — rather
than either number alone — carry the evaluation's central claim that "the architecture's
own contribution is free"?
