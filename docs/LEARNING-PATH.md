# Learning path — understand the whole implementation, in order

A guided, checkable route through the codebase. It follows the **import direction**
(downward only): every layer is understood before anything that depends on it. Tick each
box as you go. Phases 0–3 need nothing running; the **lab** enters at Phase 4; the
**deployed LLM** only at Phases 4/6 (optional).

The one sentence to carry the whole way:
> **A token is the right to push one config to the router, and only deterministic code —
> never an LLM — may honor it.** Every module boundary exists to keep that sentence true.

**Setup once:** `uv sync --all-packages` · `forge build --root contracts`
(needs [Foundry](https://getfoundry.sh)) · `containerlab deploy -t netlab/topology.clab.yml`
when you reach Phase 4.

---

## Phase 0 — The idea and the map *(read, ~1h)*

- [ ] `README.md` — the pitch + the run commands
- [ ] `docs/00-the-story.md` — every concept via the problem it solves (Ada, Bell, ticket #7)
- [ ] `docs/02-architecture.md` — the package table + import graph
- [ ] `CLAUDE.md` — the 10 hard rules. **This is "why divided" compressed**: the packages are
      *trust domains*, not size buckets. Keys only in `chainmcp` (rule 2); controller never an
      LLM (rule 1); `domain.py` imports no I/O (rule 4); shapes only from `interfaces` (rule 3).

**Check yourself:** draw the package graph from memory and name the rule that forces each edge downward.

## Phase 1 — The treaty: `interfaces` *(no stack)*

*Why it exists:* shared shapes in one dependency-free package make cross-package coupling explicit and versioned.

- [ ] Read `docs/03-interfaces.md` + `docs/03a-interfaces-walkthrough.md`
- [ ] Read the source (small): `interfaces/src/a2a_interfaces/models.py` (shapes),
      `ports.py` (the Protocols other packages plug into), `fixtures.py` (canonical values)
- [ ] Inspect: `uv run python -c "from a2a_interfaces.fixtures import CANONICAL_OFFER, CANONICAL_ENTITLEMENT_VIEW; print(CANONICAL_OFFER); print(CANONICAL_ENTITLEMENT_VIEW)"`

**Check:** what breaks, and where, if you change an `Offer` field without bumping its `v`?

## Phase 2 — The vending machine: `contracts` (Solidity)

*Why separate:* settlement must be trustless + immutable — not Python anyone can edit. "Payment = ticket, atomically" is a contract invariant.

- [ ] Read `docs/04-contract-spec.md` + `docs/04a-settlement-walkthrough.md`
- [ ] Read `contracts/src/Settlement.sol` (~230 lines — `fulfill`, `revoke`, `tokenURI`, `_issue`)
- [ ] **Drive it live** (inspect-first): `contracts/EXPLORE.md`, then `EXPLORE-settlement.md`
      → `EXPLORE-fulfill.md` → `EXPLORE-revoke.md` (start Anvil, `forge inspect`, `cast send/call` by hand)
- [ ] Gas evidence: `cd contracts && forge snapshot && cat .gas-snapshot`

**Check:** what on-chain state makes an offer single-use, and what makes `revoke` ≠ burn?

## Phase 3 — The Python packages, bottom-up *(Anvil-only where noted)*

Each notebook **builds the real component by hand**. Read the spec, then run the notebook.
Verify a notebook runs green headless with:
`uv run --group demo jupyter nbconvert --to notebook --execute e2e/notebooks/<name>.ipynb --stdout > /dev/null`

- [ ] **chainmcp** — the only key-holder (rule 2). Skim `docs/03` key-custody parts →
      run `e2e/notebooks/chain_client_explore.ipynb` *(spawns Anvil)*. Signs an EIP-712 offer,
      fulfills, reads the entitlement back, sees the tx hash.
- [ ] **netctl** — the gNMI hands. Read `docs/07-netlab.md` (run the notebook in Phase 4).
      Two provisioners (mock + real) satisfy one Protocol + one contract-test suite (rule 7).
- [ ] **controller** — the bouncer, the heart. Read `docs/05-controller-spec.md` +
      `docs/03b-lifecycle-walkthrough.md`, then the source **in this order**:
      `domain.py` (pure predicate + state machine — zero I/O, rule 4) → `auth.py` →
      `translators.py` (+ golden `controller/tests/goldens/bandwidth_ticket7.json`) →
      `service.py` → `app.py`/`wiring.py` (the HTTP edge). Run `e2e/notebooks/controller_explore.ipynb`.
- [ ] **agents** — the two LLM slots. Read `docs/06-agents-spec.md` → run
      `e2e/notebooks/agents_explore.ipynb` *(Anvil-only)*. `llm.py` is the *only* LLM-SDK import
      (ADR-001); judgment lives in exactly two places: `decision.py` and the quote node in `provider_graph.py`.

**Check:** trace one `activate()` call — which packages does it touch, and where is the exact line the LLM is *forbidden* to influence?

## Phase 4 — It all comes together *(lab required)*

`containerlab deploy -t netlab/topology.clab.yml`

- [ ] Now **run** `e2e/notebooks/netctl_explore.ipynb` against the live srl1 (policer + telemetry-export config, read back off the router)
- [ ] `docs/03c-skeleton-walkthrough.md` → `e2e/notebooks/skeleton_explore.ipynb` (the mock→chain→chain+net→full profiles)
- [ ] `e2e/notebooks/console_explore.ipynb` — builds the `Console` engine by hand, prints the real
      event stream (A2A → MCP → chain tx → predicate → gNMI). The executable twin of the dashboard.
- [ ] `docs/08-demo-dashboard.md` → `just console` (+ `just explorer` for the Otterscan block explorer).
      **Drive it:** chat to Ada, watch the trust relay, click a tx hash into the explorer, revoke.
      This is where you *see* every layer cooperate live.

**Check:** in the console event stream, name which trust domain owns each event and which ADR governs it.

## Phase 5 — Why it's decided the way it is: the ADRs *(read)*

Read now (they land harder after the code). Each is a real decision with alternatives:

- [ ] `001` LLM-serving (→ the Modal deploy, `llmserve/`) · `002` A2A SDK · `003` dashboard
- [ ] `004` chain-time as the only clock (→ the revocation showpiece)
- [ ] `005` resourceId→topology resolution · `006` lab datapath enforcement (→ what "enforced" means)
- [ ] `007` telemetry as a device-config *right* (read the revision at the top)

## Phase 6 — The evaluation, and *why* each number

*Why these experiments:* each defends one claim a skeptic raises — latency (is it slow?),
predicate-ns (is the *architecture* slow?), revocation (does the ticket govern the wire?),
gas (affordable?), adversarial (cheatable?), LLM (judgment viable?), baseline (cost of trustlessness?).

- [ ] Read `docs/09-evaluation.md` — **§1–2 first** (existence proof vs evaluation; the two honest
      definitions of "enforced" and the five simulation boundaries), then each experiment
- [ ] Read `e2e/src/e2e/experiments.py` — the harness (`TimingProvisioner` = rule 7 again; revocation uses the *real* watcher thread)
- [ ] Run `just eval` (or `uv run python -m e2e.experiments --exp predicate` for the instant, lab-free one)
- [ ] Open `e2e/notebooks/evaluation_explore.ipynb` for the five figures
- [ ] `docs/evidence/M7.1.md` — the figures inline **+ the four explain-back questions**

**Final check (the real exam):** answer the four explain-back questions in `docs/evidence/M7.1.md`.

---

## Reference (dip in, don't read cover-to-cover)

- `docs/01-implementation-plan.md` — the milestone map (order is *not* numeric)
- `docs/evidence/M*.md` — per-milestone proof with real pasted output
- `docs/05-from-scratch.md` — how the plumbing was built, step by step
- `docs/04-writing-standard.md` — the comment/doc standard the codebase follows
- `DESIGN.md` — the *original* formal plan (historical; its status banner points to where reality diverged)
- `e2e/notebooks/scratch_inspect.ipynb` — the blank bench: pre-wired imports, poke anything

## The notebooks, and what each needs

| notebook | needs | teaches |
|---|---|---|
| `chain_client_explore` | Anvil | signing, fulfill, entitlement reads |
| `agents_explore` | Anvil | the two LLM judgment slots, MCP tools |
| `controller_explore` | Anvil | predicate, auth, the session machine |
| `netctl_explore` | **lab** | the policer + telemetry-export config on srl1 |
| `skeleton_explore` | **lab** | the profiles assembling the layers |
| `console_explore` | **lab** | the whole pipeline as a live event stream |
| `evaluation_explore` | data only | the feasibility figures |
| `scratch_inspect` | — | your playground |
