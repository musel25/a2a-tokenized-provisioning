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

Open the console and press **“Ada, get me this.”** It drives the *real* pipeline —
Ada's agent negotiates with Bell over A2A, pays on-chain (real EIP-712, real ERC-721,
real tx hash), the controller authorizes, and a real policer lands on srl1 — and shows
it as a **trust relay**: the request lights up each domain (agents → chain → controller →
network) as it crosses it. The **device inspector** reads srl1's live config off the
router and iperf measures the enforced throughput (~49 Mbps). Toggle **Telemetry** for
the second service type (samples stream to a live collector). Then hit **Revoke** and
watch the relay's signal get *cut at the chain* and the throughput jump back to 100 Mbps.

Without the lab the console still runs everything real except the router lane, which says
so honestly. Events are the same `DashboardEvent` JSONL the file-tailing view uses.

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
apply_telemetry (network) forwarder: srl1 counters → Ada's collector
  telemetry: 2 samples arrived at the collector
```

Same controller, same auth, same session machine, same provisioner object — only the
translator (`translate_bandwidth` → `translate_telemetry`) and the one provisioner call
differ. That delta *is* a thesis result: the architecture generalizes across products
for the cost of one translator.

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
