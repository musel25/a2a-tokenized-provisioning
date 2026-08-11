# 08 — Demo: the operator console runbook

> **Status:** the presentation runbook. Rehearse cold, twice.
> **Companions:** `docs/00-the-story.md` (the narrative this dramatizes) ·
> `e2e/src/e2e/dashboard/` (the console as code) · ADR-003 (jury-first) ·
> `e2e/notebooks/paper.ipynb` (the same system as the paper's executable twin).

---

## The one-line pitch

*AI agents buy network services from each other; payment is atomically exchanged for an
on-chain entitlement; a deterministic controller honors the entitlement by configuring a
real router — and when the entitlement is revoked on-chain, the bandwidth dies mid-stream.*

## The operator console (M6.4 — the interactive way to run and watch it)

```sh
containerlab deploy -t netlab/topology.clab.yml   # the SR Linux lab (~1 min) — for live enforcement
just console                                       # → http://127.0.0.1:8099
just explorer                                      # optional: Otterscan → http://localhost:5100
```

**`just up` is not part of this path.** It exists for the headless lifecycle tests; the
console boots its *own* Anvil and deploys the contracts on the first action (preferring
:8545 so the explorer's tx links resolve). Running both leaves a stray chain on the port
the console wanted. Console, lab, explorer — that is the whole list.

With the explorer up, the console pins its Anvil to :8545, an `explorer ↗` pill appears,
and every tx hash in the event stream becomes a link — the jury can open the fulfill or
revoke transaction in a real block-explorer UI (Anvil implements Otterscan's `ots_` API;
the explorer reads the same chain the demo writes).

**Chat to Ada's agent** — type a request ("get me 50 Mbps under 12 TOK", or "buy the right
to configure telemetry export on srl1"). The agent reads the intent, picks the product,
and drives the *real* pipeline: it negotiates with Bell over A2A, pays on-chain (real
EIP-712, real ERC-721, real tx hash), the controller authorizes, and a real config lands
on srl1 — shown as a **trust relay** where what Ada bought lights up each domain
(agents → chain → controller → network) as it crosses it.

Two products, and the console makes the distinction the point — both are *the right to
write one config to the router*:

- **Bandwidth** → a rate **policer** (`/qos`). The inspector reads it back off srl1 and
  iperf measures the enforced throughput (~49 Mbps).
- **Telemetry** → a **dial-out export** (`/system/grpc-tunnel`): a destination naming the
  buyer's collector *and* the tunnel that dials it (ADR-008 — the destination alone is an
  address book and exports nothing). The token is the *right to configure telemetry export
  on the device*; the inspector shows both nodes the controller wrote, read straight off
  the router, with the router's own `oper-state` for the tunnel.

Then **Revoke**: the relay's signal is *cut at the chain*, the break propagates to the
router, and the config is removed (bandwidth throughput jumps back to 100 Mbps; the
telemetry tunnel then destination are deleted from srl1 and the samples stop).

**Real LLM judgment** (ADR-001 amendment): deploy the agents' model once
(`uv run modal deploy llmserve/modal_llm.py`, see `llmserve/README.md`), put the endpoint
in `.env` (`A2A_LIVE_LLM=1`), and both judgment slots go live — Bell *prices* each quote
and Ada *judges* each offer with the real `agents.decision.decide` / `QuoteDecision`
calls, so prices and reasons vary run to run and the budget slider actually matters. The
header pill shows `judgment · qwen3-4b` (green), `warming` (amber — the console warms the
container at startup), or `deterministic` (no `.env`; the demo never requires the
network). **The pill is a switch**: click it to mute/unmute live judgment mid-session —
run one provision deterministic and the next on the model to contrast the two. Without the lab the console still runs everything real except the router lane,
which says so honestly.

## Preflight — prove all four layers before you present

Every lane degrades *silently and honestly*: no lab means a `MockProvisioner`, no warm
endpoint means deterministic stand-ins. That is the right behavior on stage and the wrong
behavior five minutes before it, because a half-real demo looks exactly like a real one
until the jury asks. Four checks, each hitting a different layer. Run them in order; the
whole thing takes under a minute.

**1 · the lab** — the console resolves srl1 by container IP, so the container is the check:

```sh
docker ps --format '{{.Names}}' | grep clab-a2a     # → clab-a2a-srl1, -hostA, -hostB
docker exec clab-a2a-hostA which iperf3             # → /usr/bin/iperf3 (Beat 1's plateau)
```

**2 · the chain's prerequisites** — the console deploys the contracts itself, but only if
Foundry built them; a missing `out/` surfaces late, as a failed first action:

```sh
uv run python -c "from chainmcp.testing import anvil_available, artifacts_available; \
  print(anvil_available(), artifacts_available())"   # → True True
```

`False` on the right means `forge build --root contracts`.

**3 · the LLM** — the endpoint is scale-to-zero, so this both *checks* and *warms* it. Cold,
it takes ~60 s; warm, under a second:

```sh
source .env && curl -s -o /dev/null -w '%{http_code} in %{time_total}s\n' \
  $LLM_BASE_URL/chat/completions -H "Authorization: Bearer $LLM_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"$LLM_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"ok\"}],\"max_tokens\":5}"
# → 200 in 0.81s
```

**4 · the console's own view** — the one check that reads all four lanes at once, and the
authority if it disagrees with the three above:

```sh
just console &                                     # → http://127.0.0.1:8099
curl -s http://127.0.0.1:8099/api/status
# {"anvil":false,"lab":true,"artifacts":true,
#  "llm":{"status":"up","model":"qwen3-4b","muted":false,"live":true}, …}
```

Read it as: `lab:true` = the router lane is live (not `MockProvisioner`); `artifacts:true` =
the chain can deploy; `llm.status:"up"` = the header pill is green, `"warming"` = wait,
`"off"`/`"down"` = deterministic stand-ins. **`anvil:false` here is correct** — the chain
starts lazily on the first action, and flips to `true` with an `rpc_url` afterwards.

Then drive one full request and throw it away, so the first thing the jury sees is not the
first thing *you* see. Verify the config landed by reading the router directly, not the
console — the console reporting its own success proves less than SR Linux agreeing:

```sh
docker exec clab-a2a-srl1 sr_cli "info from state /qos" | grep -A3 a2a-ent
#   policer-template a2a-ent7-a0 { … peak-rate-kbps 50000 … }
```

Finish with **Reset stack** in the UI, which tears down the sessions and the chain, so the
rehearsal leaves no policer behind on srl1.

## The script (three beats)

All three beats are driven from the console — type the request, watch the relay.

### Beat 1 — bandwidth, the happy path

Ask Ada: *"Get me 50 Mbps from hostA to hostB, budget 12 TOK."* The stream fills:

```
admit        (agents)     Bell's admission: reserved 50 Mbps · pool 950/1000 free
fulfill      (chain)      Ada buys a 50 Mbps entitlement from Bell
apply_bandwidth (network) gNMI Set: policer 50 Mbps on srl1
  bandwidth: 100M offered → 49 Mbps (policed)            ← the plateau, live iperf
```

The plateau is the thesis's favorite picture: throughput obeys a number that lives on a
blockchain.

> **With live judgment, this beat can end in a decline — by design.** Deterministically
> Bell quotes the catalogue list price (10 TOK), comfortably under the canonical 12 TOK
> budget. Live, Bell *prices*, and the model is free to come back above 12 — in which case
> Ada correctly refuses and the run stops at `Ada decides: decline` with no purchase, no
> session, no policer. Nothing is broken; you have just watched both judgment slots do
> their job, and the on-screen reason names the two numbers.
>
> That makes it a fine beat to run *deliberately* — it is the cheapest proof that the
> budget is enforced by judgment rather than theatre. But it is a poor opener. To keep
> Beat 1 the happy path, state a budget the quote cannot beat (`…budget 25 TOK`) or raise
> the slider; to show the decline, run the canonical 12 TOK. Same request, two outcomes,
> and the pill explains which world you are in.

### Beat 2 — telemetry, "same machine, different translator"

Ask Ada: *"Buy me the right to configure telemetry export on srl1."* The point is *how
little changed*:

```
admit        (agents)     Bell's admission: reserved 1 collector slot · pool 7/8 free
apply_telemetry (network) gNMI Set: telemetry destination + tunnel on srl1 → Ada's collector
  telemetry: export a2a-ent8-a1 configured on srl1
```

The telemetry entitlement is the *right to configure telemetry export on the device*
(ADR-007): the controller writes a `grpc-tunnel destination` to srl1 — symmetric with the
bandwidth policer. Same controller, same auth, same session machine, same provisioner
object — only the translator (`translate_bandwidth` → `translate_telemetry`) and the one
provisioner call differ (a different config subtree). That delta *is* a thesis result: the
architecture generalizes across products for the cost of one translator.

### Beat 3 — the revocation finale (the jury-gold moment)

Click **Revoke entitlement ✕**. The showpiece, proven live in
`e2e/tests/test_controller_showpiece.py` and now on screen:

```
14:02  session ACTIVE     iperf 100M → 49.3 Mbps received   (policed at 50)
15:10  Bell sends revoke(7) on-chain — nothing else is touched
15:10  controller's watcher fired → session torn_down
15:10  iperf 100M → 100.0 Mbps received   (policer gone, full rate)
```

The throughput line dies mid-window because an ERC-721 flag flipped on a blockchain.
Nobody touched the router; the controller watched the chain and acted.

## The console's anatomy (ADR-003)

The **trust relay** is the paper's Fig. 1 in motion: four stations — agents · chain ·
controller · network — badged with the workflow's step numbers (1–2 / 3 / 4 / 5–6) and
R5/R6/R9–R12 requirement chips (hover for the definition), because the honest story is *which
domain is trusted to have done what*. Below it, the event stream (A2A · MCP · chain, every
tx hash a link when the explorer is up) and the device inspector reading srl1 live.

## When a lane is not live

Symptoms map to lanes one-to-one, because each degradation is announced rather than hidden.

| What you see | What it means | Fix |
|---|---|---|
| boot says `Router offline` | `lab_ipv4()` found no srl1 container → `MockProvisioner`; every other lane is still real | `containerlab deploy -t netlab/topology.clab.yml`, then **Reset stack** |
| pill reads `warming` (amber) | scale-to-zero container booting (~60 s); the console warms it at startup | wait, or preflight step 3 before opening the page |
| pill reads `deterministic` | no `.env`, or `A2A_LIVE_LLM` unset — stand-ins, by design | fill `.env` per `llmserve/README.md`, restart the console |
| pill green but prices never move | judgment muted | click the pill — it is a switch |
| `list price (LLM fallback after a schema failure)` | the endpoint answered off-schema; the console reran Bell's *same* graph deterministically rather than die | none needed mid-demo; it says so on screen |
| `Ada decides: decline` on Beat 1 | live Bell priced above the budget | expected — see the note under Beat 1 |
| first action fails on contracts | Foundry artifacts missing | `forge build --root contracts` |
| no `explorer ↗` pill, tx hashes unlinked | Otterscan down, or the console fell back off :8545 because the port was taken | free :8545, **Reset stack**, `just explorer` |
| a policer survives the demo | teardown skipped by a crash between actions | teardown is idempotent (rule 8): **Reset stack**, or re-run and revoke |

The general move is **Reset stack**, not a restart: it closes the clients, tears down every
session on the router, and stops the chain, so the next run boots clean.

## Rehearse cold, twice

The whole point of ADR-003 is that the demo replays from a cold machine without fumbling:
`containerlab deploy …`, `just console`, run the three beats, **Reset stack**, and do it
again.
