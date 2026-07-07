# 01 — Implementation plan: skeleton first, then grow

> **Status:** canonical. Supersedes the earlier milestone sketch (change: the Python
> chain client is now M1.5, inside Phase 1, so the skeleton gets its first real organ
> immediately after the contracts exist).
> **Companions:** `docs/00-the-story.md` (concepts) · `docs/03-interfaces.md` (schemas) ·
> `docs/adr/` (decisions) · `CLAUDE.md` (rules for coding sessions).

---

## A. How to use this plan

### A.1 The loop (every milestone, no exceptions)

1. **Retell gate.** Retell the linked story chapter out loud, no notes. Can't? Reread it,
   ask questions, *then* start. Code written before the concept lands is debt.
2. **Understand first.** Read the milestone's "Understand first" lines; chase anything fuzzy.
3. **Build** — small commits, milestone id in the message: `M1.3: fulfill + single-use offers`.
4. **Validate** with the exact commands listed. Outputs must match the "evidence" description.
5. **Record evidence**: copy `docs/evidence/TEMPLATE.md` → `docs/evidence/M1.3.md`, paste the
   real outputs, answer the explain-back questions *in writing* (two sentences each is fine).
6. **Done check** — tick the boxes. A milestone without evidence is not done.

### A.2 Rules for working with Claude Code (understanding is the priority)

- **Spec and tests lead.** Where the milestone says "spec-first", you co-write the
  invariants/tests before any implementation exists. You should be able to predict what a
  failing test will say before running it.
- **Explain-back rule.** After any generated file: paraphrase every function in your own
  words. Anything you can't paraphrase, you interrogate ("why this and not X?") before
  committing. The explain-back questions in each milestone are the minimum bar.
- **One milestone per session/branch.** Keeps diffs reviewable by you, which is the point.
- **`CLAUDE.md` is law** for sessions: architecture constraints live there so every session
  starts already knowing them.

### A.3 Definition of done (global)

Tests green locally **and** in CI · evidence file committed · explain-back answered ·
no new abstraction with only one implementation · interfaces untouched (or bumped +
documented in the same commit).

---

> **Status update (2026-07-07): the plan is complete — all milestones M0.1 → M6.5 are
> landed, each with a green CI run and a `docs/evidence/M<id>.md`.** The four skeleton
> versions were reached in order; skeleton v4 (real agents drive everything) is the
> system. Environment caveats recorded in the relevant evidence: the shared box serves
> the LLM at ~140 s/decision (M5.1/M5.6 live runs are opt-in, contract proven
> deterministically); demo *recording* (M6.5) is the one inherently-manual step.

## B. The backbone: skeleton versions

| Version | What's real | What's fake | Reached at |
|---|---|---|---|
| **v0** | the lifecycle itself, the interfaces | chain, network, controller logic minimal, agents scripted | end of Phase 0 ✓ |
| **v1** | + contracts on Anvil, Python chain client | network, agents; controller still the stub | end of Phase 1 ✓ |
| **v2** | + real SR Linux lab via netctl | agents; controller still the stub | end of Phase 3 ✓ |
| **v3** | + the real controller (predicate, auth, translators, watcher) | agents (decisions scripted) | end of Phase 4 ✓ |
| **v4** | + LLM agents, MCP tools, A2A discovery — **the system** | nothing | end of Phase 5 ✓ |

The skeleton lifecycle test runs in CI forever, in `mock` profile. Profiles select adapters:
`SKELETON_PROFILE = mock | chain | chain+net | full` (real profiles run locally; CI runs
`mock` + all unit and contract tests).

---

## C. Milestone map

(~ = focused working days; double them for thesis-writing weeks.)

| Id | Milestone | ~ | Evidence | Story ch. |
|---|---|---|---|---|
| M0.1 | Repo scaffold, uv workspace, CI | 0.5 | green Actions run on a no-op | 9 |
| M1.1 | Foundry + Anvil hello world | 0.5 | forge test ×3, cast call/logs | 1, 4 |
| M0.2 | Interfaces as code (pydantic + ports) | 1 | round-trip tests on Ada's values | 9 |
| M0.3 | **Walking skeleton v0** (all fakes) | 1 | lifecycle + revocation tests green in CI | all |
| M1.2 | Entitlement storage + ERC-721 (spec-first) | 1 | forge tests: issue, fields, ownerOf | 2 |
| M1.3 | EIP-712 offers + atomic `fulfill` + single-use | 2 | revert-path tests, fuzz, atomicity proof | 4 |
| M1.4 | revoke, events, on-chain tokenURI, deploy script | 1 | warp tests; decoded data: URI | 8 |
| M1.5 | Python chain client + **skeleton v1** | 1.5 | cross-stack signature test vs Anvil | 4, 5 |
| M2.1 | Containerlab topology up | 0.5 | clab inspect; ping hostA→hostB | 6 |
| M2.2 | Bandwidth limited **by hand** | 1–2 | iperf3 before ≫ after ≈ 50 Mbps | 6 |
| M2.3 | Telemetry subscribed **by hand** (gnmic) | 0.5 | sample lines every 10 s | 7 |
| M3.1 | pygnmi smoke (Get + Set) | 0.5 | script reads oper-status; Set survives | 6 |
| M3.2 | `apply_bandwidth`/`teardown` lib + mock parity | 1 | same iperf evidence via one call | 6 |
| M3.3 | `apply_telemetry` (ADR-007, revised → device export config) | 1 | ticket configures a `grpc-tunnel` export on srl1 via one call | 7 |
| M3.4 | **Skeleton v2** (chain+net profile) | 0.5 | lifecycle green against Anvil + lab | 9 |
| M4.1 | Controller domain: predicate + state machine | 1 | unit tests incl. all deny paths | 5 |
| M4.2 | Challenge–response auth | 0.5 | replayed proof rejected (test) | 5 |
| M4.3 | Two translators (golden files) | 1 | sample entitlement → exact expected calls | 5, 7 |
| M4.4 | Controller HTTP API (FastAPI) | 1 | httpx tests of §3 endpoints | 5 |
| M4.5 | Real adapters + Revoked watcher → **skeleton v3** | 1.5 | on-chain revoke kills a live lab session | 8 |
| M5.1 | LLM client (ADR-001) + structured decision | 0.5 | 20/20 valid decisions vs local Ollama | 5 |
| M5.2 | Consumer LangGraph graph (tool stubs) | 1 | transcript shows full happy path | 9 |
| M5.3 | Provider graph + admission control | 1 | over-capacity quote is declined | 8 |
| M5.4 | MCP servers: chainmcp, ctrl-mcp | 1.5 | agent buys via tools on Anvil | 3, 5 |
| M5.5 | A2A: cards, skills, registry (pinned SDK) | 1.5 | card fetched; offer over the wire | 9 |
| M5.6 | **Skeleton v4** — agents drive everything | 1 | full agent-driven run, real stack | all |
| M6.1 | One-command bring-up | 1 | `just up` → healthchecks pass | 9 |
| M6.2 | Bandwidth e2e + auto-teardown at t1 | 1 | iperf plateau; teardown at chain-time t1 | 6 |
| M6.3 | Telemetry e2e (second serviceType) | 1 | second lifecycle green, core reused | 7 |
| M6.4 | Dashboard v1 (wireframe + ADR-003) | 2 | a live run watchable end-to-end | epilogue |
| M6.5 | Demo script + revocation showpiece + recording | 1 | cold replay twice in a row | 8 |
| M7.1 *(post-plan)* | Evaluation: harness + campaign + docs/09 | 1 | 7 experiments on the real stack; adversarially audited; `e2e/runs/eval/` committed | docs/09 |

---

## D. Phase details

### Phase 0 — Foundations (week 1) → skeleton v0

#### M0.1 — Repo scaffold, uv workspace, CI

**Goal.** A home where every later milestone has a slot, and a CI that will never again be
"added later".

**Understand first.** A *monorepo with bounded packages*: one git repo, many packages,
strict import direction (ch. 9's cast list). CI = a robot that runs your tests on every
push so integration drift is caught the day it happens. `uv` = the Python package/workspace
manager (fast, lockfile-based); a *workspace* lets the packages share one lockfile while
staying separate packages.

**Build.**
```
a2a-provisioning/
├── CLAUDE.md  DESIGN.md  README.md  Justfile
├── docs/{00-the-story.md, 01-implementation-plan.md, 03-interfaces.md, adr/, evidence/}
├── contracts/            ← from M1.1 (forge init)
├── interfaces/           ← Python pkg `a2a_interfaces` (M0.2)
├── e2e/                  ← skeleton + lifecycle tests (M0.3)
├── chainmcp/ netlab/ netctl/ controller/ agents/   ← empty, with README stubs
├── pyproject.toml        ← [tool.uv.workspace] members = ["interfaces", "e2e"]
└── .github/workflows/ci.yml
```
CI: checkout (submodules recursive) → setup-uv → `uv sync` → `uv run pytest` →
foundry-toolchain → `forge test` in `contracts/` when it exists.

**Validate.** Push; the Actions run is green. `tree -L 2` matches the layout.

**Watch for.** Foundry installs libs as git submodules — clone/CI must init them. Don't
add packages to the workspace before they exist; uv errors on missing members.

**Explain-back.** (1) Why does the controller package never import from `chainmcp`
directly — what sits between them? (2) What exactly does CI re-run on every push?

**Done when** ☐ Actions green ☐ layout committed ☐ evidence file `M0.1.md`.

---

#### M1.1 — Foundry + Anvil hello world

Spec: a `Counter` contract with an `Incremented` event, a deploy script, and a `cast`
round-trip — delivered on branch `m1.1-foundry-hello`, inside `contracts/`. Evidence:
`forge test` ×3 green, `cast call` returns the incremented value, `cast logs` shows the
event.

**Explain-back.** (1) Transaction vs call — which one will `fulfill` be, which one will the
controller's reads be, and why does that matter for cost and trust? (2) What is an event
*for*, in one sentence, given the controller's `Revoked` watcher?

---

#### M0.2 — Interfaces as code

**Goal.** `docs/03-interfaces.md` stops being prose: every cross-boundary shape becomes a
validated Python type, and Ada's example values become shared test fixtures.

**Understand first.** A *published language* only works if it's executable — a schema that
can reject bad data at the border. We use **pydantic v2**: define the shape once, get
validation + JSON (de)serialization + schema export. The alternative (bare dicts) means
every package re-validates by hand and drifts. Also meet `typing.Protocol`: an interface a
class satisfies by shape, not inheritance — this is how ports are expressed in Python.

**Build.** `interfaces/src/a2a_interfaces/`
- `models.py`: `ServiceNeed` (discriminated union on `kind`), `Offer`, `SignedOffer`,
  `DecisionOutput`, `EntitlementView` (+ `BandwidthParams | TelemetryParams`),
  `ResolvedPath`, `ResolvedNode`, `ApplyResult`, `SessionState`, `ErrorCode` — exactly
  §1–§6 of docs/03.
- `ports.py`: `EntitlementReader`, `NetworkProvisioner` Protocols (§4, §5).
- `fixtures.py`: **the canonical example** — Ada `0xf39F…2266`, Bell `0x7099…79C8`,
  ticket #7's fields, the 10 TOK offer, the telemetry need. One source of truth for tests
  *and* docs.
- Keep this package dependency-light (pydantic only). Keccak/EIP-712 helpers belong to
  `chainmcp`, not here.

**Validate.** `uv run pytest interfaces/` — round-trip (model → JSON → model, equal),
rejection tests (negative capacity, unknown kind, malformed address pattern).

**Watch for.** Don't "improve" the schemas while transcribing — any change goes to
docs/03 + `v` bump in the same commit. Resist adding behavior; this package is shapes.

**Explain-back.** (1) Why must validation live at the boundary rather than inside each
package? (2) What's the difference between a Protocol and a base class, and why does the
controller's testability depend on it?

**Done when** ☐ all §1–§6 shapes exist ☐ fixtures match the story's numbers ☐ tests green.

---

#### M0.3 — Walking skeleton v0

**Goal.** The *entire play with cardboard props*: Ada's twelve epilogue lines execute as
one test, end to end, with everything fake — and CI runs it forever after.

**Understand first.** Reread story ch. 9's walking-skeleton section. The fakes' job is to
be *dumb*: a FakeChain is a dict, not a mini-Ethereum. The skeleton proves the
*architecture's joints*, not any component's muscle. Also: this is where you first write
the **authorization predicate** — naively, ~10 lines — so the concept is in your hands two
phases before the real controller exists.

**Build.** `e2e/skeleton/`
- `fakes.py`: `FakeChain` (entitlements dict, balances, consumed-salt set; `fulfill()`
  enforces single-use and "atomicity" by doing all-or-nothing in Python),
  `FakeNet` (records `apply_*`/`teardown` calls; satisfies `NetworkProvisioner`),
  `FakeClock` (the chain time you can advance).
- `stub_controller.py`: nonce issue/check (a set), the naive predicate (owner, window vs
  FakeClock, revoked flag, scope, conflict), calls the provisioner port.
- `scripted_agents.py`: provider returns a canned `SignedOffer` (signature `"0xFAKE"` —
  fakes don't verify), consumer's `decide()` returns the fixture decision.
- `e2e/tests/test_lifecycle.py`: happy path asserting — owner of #7 is Ada, Bell +10 TOK,
  salt consumed, FakeNet holds the 50 Mbps config; advance clock past t1 → tick → torn
  down. Plus: **replay test** (same offer twice → rejected) and **revocation test**
  (flip flag mid-session → tick → torn down). Print the narration lines as it runs.

**Validate.** `uv run pytest e2e/ -v` — test names read like the lifecycle. CI green.

**Watch for.** Scope creep into the fakes (no balances ledger beyond two numbers, no gas,
no signatures). If a fake exceeds ~40 lines, it's trying to be real.

**Explain-back.** (1) Why is it a *feature* that FakeChain is 30 lines? (2) Which future
phase replaces which fake — name all four swaps.

**Done when** ☐ 3 lifecycle tests green in CI ☐ narration printed ☐ predicate exists and
you wrote it.

*End of Phase 0: also assemble `docs/02-architecture.md` by drawing what now exists —
diagrams are honest when they describe running code.*

---

### Phase 1 — Settlement, real (weeks 2–3) → skeleton v1

*Phase opener: we co-write `docs/04-contract-spec.md`, starting from this invariants list —
**I1** only `fulfill` mints · **I2** each offer salt fulfillable once · **I3** payment and
mint happen atomically or not at all · **I4** only the issuer can revoke · **I5** revoke is
a flag, never a burn · **I6** terms in storage are immutable after mint · **I7** `tokenURI`
is derived purely from storage · **I8** an expired/revoked entitlement still exists and is
readable. Every invariant becomes at least one Foundry test. Spec → tests → code.*

#### M1.2 — Entitlement storage + ERC-721 (spec-first)

**Understand first.** ERC-721 in one line: a standard contract interface for "registry of
unique tokens with owners" — we inherit **OpenZeppelin's** audited implementation rather
than hand-rolling ownership bookkeeping (you get `ownerOf`, transfers, approvals for
free; you add what's yours: the Entitlement struct). Also meet the *test harness pattern*:
the mint stays `internal` (I1 — only `fulfill` may mint), so tests use a tiny
`SettlementHarness` that exposes it. No test-only functions in production code.

**Build.** `forge install OpenZeppelin/openzeppelin-contracts`; `src/Settlement.sol`:
`contract A2ASettlement is ERC721` + `struct Entitlement` (exactly docs/03 §2),
`mapping(uint256 => Entitlement) public entitlements`, `_issue(...) internal returns (uint256)`,
incrementing id. `test/Settlement.t.sol` + harness: fields stored verbatim, `ownerOf`,
ERC-721 transfer moves ownership (and note for ch. 8: terms don't change when it moves).

**Validate.** `forge test -vv` — name tests after invariants: `test_I1_onlyFulfillMints`...

**Watch for.** Pin solc in `foundry.toml`. The auto-generated public getter for a struct
mapping returns a tuple, not the struct — fine, but know it.

**Explain-back.** (1) What does OZ's ERC721 give you that you didn't write? (2) Why a
harness instead of a `public mintForTest`?

---

#### M1.3 — EIP-712 offers + atomic `fulfill` + single-use

**Understand first.** Reread story ch. 4 — this milestone *is* that chapter. New
mechanics: OZ's `EIP712` base computes the domain separator (name `"A2AProvisioning"`,
version `"0"` — **must match docs/03 §2.1 exactly**, or every Python-made signature will
fail in M1.5); `ECDSA.recover` turns (hash, signature) back into the signer's address.
One rule of EIP-712 struct hashing that bites everyone: **dynamic types (`bytes params`,
`string`) are hashed (`keccak256(...)`) inside the struct hash**, not embedded raw.
Custom errors (`error OfferExpired();`) instead of strings: cheaper and they make tests
crisp.

**Build.** `src/MockTOK.sol` (OZ ERC20 + open `faucet(address,uint256)`). In Settlement:
`OFFER_TYPEHASH`, `hashOffer(Offer)`, `mapping(bytes32 => bool) consumed`,
`fulfill(Offer calldata o, bytes calldata sig)`: check `validUntil` vs `block.timestamp` →
recover signer == `o.provider` → consumer binding (`o.consumer == 0 || msg.sender`) →
`!consumed` → mark consumed → `transferFrom(msg.sender, o.provider, o.price)` →
`_issue(...)` → emit `OfferConsumed`, `EntitlementMinted` → return id.

**Validate.** Foundry: happy path (balances moved, owner, fields); replay →
`OfferAlreadyUsed`; any tampered field → `BadSignature`; expired → revert; **the atomicity
proof**: no allowance → `vm.expectRevert`, then assert *neither* NFT exists *nor* salt is
consumed (the whole world rolled back). Fuzz salts and prices. Sign in tests with
`vm.sign(providerKey, digest)`.

**Watch for.** The `bytes params` keccak rule above (the classic bug); field *order* in
the typehash string must match the struct; use OZ ECDSA (it guards signature
malleability for you — ask Claude Code to explain what malleability is when you get
there). Also: the skeleton's `FakeChain.fulfill` (post-M0.3 review hardening) already
encodes the check order — expired → consumer binding → salt → funds — with one e2e
deny-path test per check (`docs/04` §3, I2/I3). Keep the contract's revert order aligned
with the fake, and name the custom errors after the fake's exceptions (`OfferExpired`,
`WrongConsumer`, `OfferAlreadyUsed`) so the parity is legible.

**Explain-back.** (1) Walk the six effects of `fulfill` and say what happens to each if
step four reverts. (2) Why is the salt ledger on-chain rather than in the provider's
database?

---

#### M1.4 — revoke, events, on-chain tokenURI, deploy script

**Understand first.** Expiry passive, revocation active (story ch. 8). `vm.warp` = time
travel in tests — this is ADR-004 paying off: expiry tests without `sleep`. On-chain
`tokenURI`: build a `data:application/json;base64,...` string from storage (OZ `Base64`,
`string.concat`) — the ticket's fine print with no web server to 404.

**Build.** `revoke(id)` with `onlyIssuer` check + `Revoked` event; `tokenURI(id)`
rendering issuer/serviceType/window/revoked from storage; `script/Deploy.s.sol`
broadcasting MockTOK + Settlement and writing `contracts/deployments/anvil.json` (addresses; Foundry cannot write above its own root — see M1.4 evidence) — the
artifact every Python package will read.

**Validate.** Warp past `endTime`, assert a view of your choice reflects it; non-issuer
revoke reverts; `cast call ... "tokenURI(uint256)" 1`, base64-decode, see the JSON.
`just deploy-local` (script: start/expect Anvil, run forge script) leaves a valid
`contracts/deployments/anvil.json`.

**Explain-back.** (1) Why is revoke a flag and not a burn? (2) Who *acts* on expiry, given
that the chain does nothing at 16:00?

---

#### M1.5 — Python chain client + skeleton v1

**Understand first.** The first *adapter*: `ChainClient` implements the `EntitlementReader`
Protocol from M0.2, plus the write/signing operations, using **web3.py** + **eth-account**.
The single most failure-prone seam in the whole project is Python-signs / Solidity-verifies
— so the milestone's centerpiece is the **cross-stack signature test**: Python builds and
signs the EIP-712 offer, Solidity's `fulfill` accepts it, against a live Anvil. When that's
green, chapters 4 and 5 are physically true. Owner-proofs (the `a2a-activate|...` string)
use simple message signing (EIP-191); note the controller will verify those *in Python*
(`Account.recover_message`) — no Solidity involved.

**Build.** `chainmcp/src/chainmcp/client.py`: reads `contracts/deployments/anvil.json` + ABI from
`contracts/out/`; implements `owner_of`, `get` (ABI-decode `params` per serviceType into
the pydantic views), `chain_time` (latest block timestamp), `watch_revoked` (background
log polling, ~1 s); write side: `faucet`, `approve_and_fulfill(signed_offer)`,
`sign_offer(offer)` (typed-data signing with the same domain), `sign_activation_proof(...)`.
Pytest fixture that launches Anvil as a subprocess + deploys. Then: skeleton profile
`chain` swaps FakeChain → ChainClient + real contracts.

**Validate.** `uv run pytest chainmcp/` incl. the cross-stack test;
`SKELETON_PROFILE=chain uv run pytest e2e/` green — **skeleton v1**: the 10 TOK and ticket
#7 in your lifecycle test are now real on-chain state.

**Watch for.** Domain mismatch symptoms = `BadSignature` with everything "looking right" —
diff name/version/chainId/verifyingContract first, always. ABI tuple field order for the
Offer struct. Regenerate ABIs from `contracts/out/` (never copy-paste).

**Explain-back.** (1) Why does the cross-stack test exist — what class of bug can nothing
else catch? (2) Which Protocol does ChainClient satisfy, and who depends on it?

---

### Phase 2 — The lab, by hand (week 4)

*Phase opener: start `docs/07-netlab.md`; every recipe you derive gets captured there
verbatim — the doc IS the deliverable of this phase, alongside your own competence.*

- **M2.1 Topology up.** `netlab/topology.clab.yml`: one SR Linux (`srl1`,
  `ghcr.io/nokia/srlinux`) between two Linux hosts (`ghcr.io/srl-labs/network-multitool`
  — has iperf3): hostA—e1-1 srl1 e1-2—hostB, addressed per docs/07. *Understand:*
  Containerlab = story ch. 6's flight simulator; default SR Linux creds are in its docs.
  *Validate:* `sudo containerlab deploy`, `containerlab inspect`, ping hostA→hostB.
  *Watch for:* SR Linux needs ~2 GB RAM and ~a minute to boot; configure basic interface
  addressing/routing before expecting pings.
- **M2.2 Bandwidth by hand.** Derive the SR Linux QoS recipe (policer template applied to
  the interface) from Nokia's docs — *deliberately by hand on the CLI*: you cannot
  automate a device you can't drive manually. This is the steepest learning curve of the
  project; budget the full two days without guilt. *Validate:* iperf3 hostA→hostB before
  (whatever the unshaped path gives — likely hundreds of Mbps+) and after (**≈ 50 Mbps
  plateau**). Screenshot both; this is the thesis's favorite picture. *Explain-back:* where
  exactly in the packet path does the policer act, and why did we pick that interface?
- **M2.3 Telemetry by hand.** Install `gnmic`; subscribe to
  `/interface[name=ethernet-1/1]/statistics`, sample-interval 10 s, watch counters stream.
  *Understand:* this is gNMI's third verb, and chapter 7's entire product, seen raw.
  *Watch for:* SR Linux gNMI speaks TLS with a self-signed cert — skip-verify is fine in
  the lab and a one-line honesty note in docs/07.

---

### Phase 3 — netctl: the hands (weeks 5–6) → skeleton v2

*Phase opener decision to settle (flagged, not yet decided): SR Linux telemetry is
dial-in (collector connects to router). So `apply_telemetry` either (a) runs a small
provider-side forwarder: subscribe to the router, relay samples to the consumer's
collector endpoint, or (b) requires the consumer's collector to dial in directly (then
"activation" = opening access + handing connection details). Default leaning: (a) — it
keeps the consumer's experience "samples arrive at my endpoint". Decide → ADR-007 (the ADR-006 slot went to the lab-datapath decision made in M2.2).*

- **M3.1 pygnmi smoke.** A 30-line script: connect (skip-verify), Get an interface
  oper-status, Set a description, Get it back. *Explain-back:* what is the YANG path and
  why is `paths.py` (one constants file) a rule?
- **M3.2 Bandwidth provisioning lib.** `netctl/src/netctl/`: `GnmiProvisioner` implementing
  `NetworkProvisioner` — `apply_bandwidth(session_id, ResolvedPath, capacity_bps, qos_class)`
  encodes M2.2's recipe as gNMI Sets; `teardown(session_id)` removes it **idempotently**
  (call twice → second is a no-op success). `MockProvisioner` already exists in e2e —
  promote it here, and write **one shared contract-test suite that runs against both**
  (mock parity = same behavior at the port). *Validate:* the M2.2 iperf evidence,
  reproduced by a single function call; `pytest netctl/` green for both implementations.
- **M3.3 Telemetry provisioning.** Implement per ADR-007. *Validate:* one call → a dummy
  collector (netcat or 20-line asyncio server) prints samples at the interval; teardown
  stops them.
- **M3.4 Skeleton v2.** Profile `chain+net`: FakeNet → GnmiProvisioner. The lifecycle test
  now leaves a real policer on a real router and removes it at t1. *Watch for:* the
  skeleton must clean up even when a test fails (pytest fixture finalizers) — a lab full
  of zombie policers makes every later run lie.

---

### Phase 4 — The real controller (weeks 7–8) → skeleton v3

*Phase opener: co-write `docs/05-controller-spec.md` — the predicate (verbatim from
DESIGN §7.4), the session state machine diagram
(`requested → authorized → active → torn_down`, `failed` from anywhere), translator I/O
tables, the auth message format.*

- **M4.1 Pure domain.** `controller/src/controller/domain.py`: the predicate as a pure
  function over (`EntitlementView`, request, `chain_time`, session table) returning
  `ok | ErrorCode`; the state machine as data + transition function. Port the skeleton's
  naive version, then harden: every deny path (wrong owner, early, late, revoked,
  out-of-scope, conflict) gets a named test. Zero I/O imports in this file — enforced by
  the explain-back: *prove* it by listing the imports. 
- **M4.2 Auth.** Nonce store (issue, single-use, expiry vs chain time), proof string
  builder/parser, `Account.recover_message` verification against `owner_of`. Test: the
  same proof replayed → `E_NONCE_REUSED`.
- **M4.3 Translators.** `translate_bandwidth(view, resource_map) → [ProvisionerCall]`,
  same for telemetry; **golden-file tests**: fixture entitlement in → exact expected call
  list out (goldens reviewed by eye once, then guarded forever).
- **M4.4 HTTP API.** FastAPI app exposing docs/03 §3 exactly; dependency-inject the ports;
  httpx tests against fakes. *Watch for:* the API layer contains no logic — it parses,
  calls domain, maps `ErrorCode` → status. If an `if` about entitlements appears here,
  it's in the wrong file.
- **M4.5 Wire + watch → skeleton v3.** Compose ChainClient + GnmiProvisioner + resource_map
  into the app; `watch_revoked` → teardown; expiry task (asyncio timer that wakes and
  re-checks `chain_time` — ADR-004 in code). *Validate (the showpiece rehearsal):* start a
  real session, `cast send ... "revoke(uint256)" 7` from Bell, watch the controller log the
  event and the iperf stream die mid-window. Evidence: that log + iperf timeline.

---

### Phase 5 — Agents: the brains (weeks 9–11) → skeleton v4

*Phase opener: co-write `docs/06-agents-spec.md` (graph diagrams, decision schemas, prompt
policy) and pin versions: `a2a-sdk`, MCP libs — checking current docs at that moment, not
memory (ADR-002).*

- **M5.1 LLM client + decision node.** OpenAI-compatible client from env (ADR-001
  profiles); `decide(need, offer) → DecisionOutput` with pydantic validation + bounded
  retries; *Validate:* 20/20 schema-valid runs against local Ollama (record the model
  tag); same test passes pointed at any other endpoint. *Explain-back:* why does the
  validator make backend differences irrelevant?
- **M5.2 Consumer graph.** LangGraph: discover → request quote → decide → settle →
  activate(3 calls) → report; tools as plain Python stubs first (graphs before MCP — two
  new technologies never land in the same milestone). *Validate:* transcript of a full
  happy path; a `decline` decision exits gracefully.
- **M5.3 Provider graph.** Receive need → admission control (a capacity ledger per window;
  over-capacity → the §1.2 decline) → build offer → `sign_offer`. *Validate:* request
  60 Mbps twice against a 100 Mbps ledger → second declines (ch. 8's no-overselling,
  as a test).
- **M5.4 MCP servers.** Wrap ChainClient as `chainmcp` (per-agent instance, that agent's
  key — the custody rule), controller API as `ctrl-mcp`; switch graphs from stubs to MCP
  tools. *Validate:* an agent-driven purchase mints on Anvil end to end via tools.
- **M5.5 A2A.** Provider A2A servers (cards + `quote_*` skills) on :9101/:9102, consumer
  client + `registry.json`; SDK imports confined to `a2a_adapter.py` per side. *Validate:*
  `curl` the agent card; a quote travels over the wire; tampering one offer field in
  transit → M1.3's `BadSignature` catches it (end-to-end integrity demo!).
- **M5.6 Skeleton v4.** Scripted agents → real agents in the `full` profile. The skeleton
  test *is now the system test.* *Watch for:* nondeterminism — the LLM may decline; the
  test asserts *valid behavior*, not one fixed path (assert schema + invariants, branch on
  decision).

---

### Phase 6 — e2e, demo, dashboard (weeks 12–13)

- **M6.1 One-command bring-up.** `just up`: Anvil → deploy → lab → controller → providers
  → (consumer on demand); healthchecks; `just down` cleans everything. Plain processes
  (process-compose or your tmux) — containers only where they already are.
- **M6.2 / M6.3 The two e2e runs.** Bandwidth with iperf evidence + auto-teardown at
  chain-time t1; then telemetry — *measure and write down* how little changed (files
  touched, lines) — that delta is a thesis result.
- **M6.4 Dashboard v1.** Components append `DashboardEvent` JSONL to `e2e/runs/<ts>/`
  (schema added to interfaces, `v` bump); Streamlit tails it into the wireframe layout:
  stepper, narration line (the epilogue's sentences, literally), three trust-domain
  columns, step-through + auto modes (ADR-003).
- **M6.5 Demo script + recording.** The narrative: bandwidth happy path → telemetry
  ("same machine, different translator") → **revocation finale** (the jury-gold moment:
  Bell pulls the flag, the throughput line dies mid-window). Record it; rehearse cold,
  twice.

---

## E. Documents written along the way

| When | Document |
|---|---|
| end of Phase 0 | `02-architecture.md` (draw what runs) |
| start of Phase 1 | `04-contract-spec.md` (invariants → tests) |
| Phase 2 (continuously) | `07-netlab.md` (topology + the two manual recipes) |
|  start of Phase 3 | ADR-007 telemetry delivery model |
| start of Phase 4 | `05-controller-spec.md` |
| start of Phase 5 | `06-agents-spec.md` + version pins |
| Phase 6 | `08-demo-dashboard.md` finalized · `09-test-plan.md` = the evidence index |
| skipped unless needed | `01-requirements.md` (the story + this plan already carry it) |

---

## F. Calendar sketch (→ defense, mid-September)

Wk1 Phase 0 · Wk2–3 Phase 1 · Wk4 Phase 2 · Wk5–6 Phase 3 · Wk7–8 Phase 4 ·
Wk9–11 Phase 5 · Wk12–13 Phase 6 · Wk14+ buffer, thesis integration, rehearsals.
Thesis writing overlaps from Phase 4 onward — every evidence file is a results paragraph
waiting to be prose.

## G. If time runs short: the cut order

Cut in this order, never the reverse: dashboard polish (keep a minimal live table) →
provider admission-control sophistication (fixed single-number capacity) → telemetry
depth (keep the lifecycle real, simplify the forwarder). **Never cut:** contract tests,
predicate deny-path tests, the bandwidth e2e with iperf evidence, the revocation demo.
