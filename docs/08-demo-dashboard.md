# 08 — Demo & dashboard: the runbook (Phase 6)

> **Status:** the demo script (M6.5) + the dashboard guide (M6.4). Rehearse cold, twice.
> **Companions:** `docs/00-the-story.md` (the narrative this dramatizes) ·
> `e2e/src/e2e/demo.py` (the demo as code) · ADR-003 (dashboard, jury-first).

---

## The one-line pitch

*AI agents buy network services from each other; payment is atomically exchanged for an
on-chain ticket; a deterministic controller honors the ticket by configuring a real
router — and when the ticket is revoked on-chain, the bandwidth dies mid-stream.*

## The operator console (M6.4 — the interactive way to run and watch it)

```sh
containerlab deploy -t netlab/topology.clab.yml   # the SR Linux lab (~1 min) — for live enforcement
just console                                       # → http://127.0.0.1:8099
```

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
- **Telemetry** → a **dial-out export destination** (`/system/grpc-tunnel`). The token is
  the *right to configure telemetry export on the device*; the inspector shows the
  `grpc-tunnel destination` the controller wrote, read straight off the router.

Then **Revoke**: the relay's signal is *cut at the chain*, the break propagates to the
router, and the config is removed (bandwidth throughput jumps back to 100 Mbps; the
telemetry export destination is deleted from srl1).

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

## The file-tailing view (headless / no browser)

```sh
uv run python -m e2e.dashboard.demo_run                          # writes the epilogue as events
uv run --group demo streamlit run e2e/src/e2e/dashboard/app.py   # three-column tail
```

Local Ollama for the agents' judgment (ADR-001, defense-day rule — no network in the
room): `ollama serve` with a model that answers fast enough to feel live.

## The script (three beats)

### Beat 1 — bandwidth, the happy path (M6.2)

`uv run python -m e2e.demo` runs it; the narration prints and the dashboard fills:

```
fulfill      (chain)      Ada buys a 50 Mbps ticket from Bell
apply_bandwidth (network) gNMI Set: policer 50 Mbps on srl1
  bandwidth: 100M offered → 49.1 Mbps (policed)          ← the plateau, live iperf
teardown     (network)    window ends → policer removed
  bandwidth: after teardown → 100.0 Mbps (full)          ← the ticket expired, service gone
```

The plateau is the thesis's favorite picture: throughput obeys a number that lives on a
blockchain.

### Beat 2 — telemetry, "same machine, different translator" (M6.3)

The same run continues into telemetry — and the point is *how little changed*:

```
apply_telemetry (network) gNMI Set: telemetry export destination on srl1 → Ada's collector
  telemetry: export a2a-demo-tel configured on srl1
```

The telemetry ticket is the *right to configure telemetry export on the device*
(ADR-007): the controller writes a `grpc-tunnel destination` to srl1 — symmetric with the
bandwidth policer. Same controller, same auth, same session machine, same provisioner
object — only the translator (`translate_bandwidth` → `translate_telemetry`) and the one
provisioner call differ (a different config subtree). That delta *is* a thesis result: the
architecture generalizes across products for the cost of one translator.

### Beat 3 — the revocation finale (M4.5, the jury-gold moment)

The showpiece, proven live in `e2e/tests/test_controller_showpiece.py` and narrated:

```
14:02  session ACTIVE     iperf 100M → 49.3 Mbps received   (policed at 50)
15:10  Bell sends revoke(7) on-chain — nothing else is touched
15:10  controller's watcher fired → session torn_down
15:10  iperf 100M → 100.0 Mbps received   (policer gone, full rate)
```

The throughput line dies mid-window because an ERC-721 flag flipped on a blockchain.
Nobody touched the router; the controller watched the chain and acted.

## The dashboard (M6.4, ADR-003)

Three columns — **chain · controller · network** — the trust domains, because the honest
story is *which domain is trusted to have done what*. The agent judgment (the two LLM
slots) is tinted apart. The current narration sits on top, in the epilogue's own words.
Events are JSONL under `e2e/runs/<ts>/events.jsonl` (docs/03 §8) — append-only, so a
crashing run is still readable, and `cat` works when there's no projector.

## Rehearse cold, twice

The whole point of ADR-003 and `just up`/`just down` is that the demo replays from a cold
machine without fumbling. Run it start to finish, `just down`, and do it again.
