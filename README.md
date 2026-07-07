# a2a-tokenized-provisioning

AI agents buy network services (bandwidth, telemetry) from each other; payment is
**atomically** exchanged for an ERC-721 entitlement via a settlement smart contract; a
deterministic controller honors the entitlement by configuring real SR Linux routers via
gNMI. Thesis: the settlement pattern is **service-agnostic** — two genuinely different
services flow through identical settlement and authorization machinery, and only the
last-mile translator differs.

The running example: Ada (a consumer agent) buys 50 Mbps on path A→B from Bell (a provider
agent) for 10 TOK; one atomic transaction mints entitlement **#7** to Ada, and a
deterministic controller honors it by shaping the router — no human, no prior trust.

## Read first, in order

1. [`docs/00-the-story.md`](docs/00-the-story.md) — every concept, introduced by the problem it solves
2. [`docs/03-interfaces.md`](docs/03-interfaces.md) — the precise schemas (the published language)
3. [`docs/01-implementation-plan.md`](docs/01-implementation-plan.md) — milestones and the current state
4. [`docs/adr/`](docs/adr/) — one page per architectural decision
5. [`DESIGN.md`](DESIGN.md) — the full formal plan

## Packages (import direction: downward only)

| Package | Job |
|---|---|
| [`interfaces`](interfaces/) | shapes + ports — the treaty every border agrees on |
| `contracts` | Solidity settlement: the vending machine (from M1.1) |
| [`chainmcp`](chainmcp/) | chain adapter + signing; the **only** key holder |
| [`netlab`](netlab/) | Containerlab + SR Linux: the miniature internet |
| [`netctl`](netctl/) | gNMI hands; topology-agnostic |
| [`controller`](controller/) | the bouncer: predicate, auth, translators — never an LLM |
| [`agents`](agents/) | LangGraph brains; LLM judgment at exactly two points |
| [`e2e`](e2e/) | the stage: skeleton, lifecycle tests, dashboard |
| [`llmserve`](llmserve/) | the agents' LLM, deployed (Modal vLLM); infra, not imported |

## Run the live demo — the operator console

```sh
# one-time setup
uv sync --all-packages                             # python workspace
forge build --root contracts                       # contract artifacts (needs Foundry)

# each session
containerlab deploy -t netlab/topology.clab.yml    # the network (SR Linux srl1 + hosts)
just console                                       # → http://127.0.0.1:8099
just explorer                                      # optional: block explorer → http://localhost:5100
```

Open the console, tell Ada what you want ("get me 50 Mbps under 12 TOK"), and watch the
request cross agents → chain → controller → router, live. `Revoke` kills it mid-window.
With the explorer up, every tx hash in the event stream links into Otterscan — inspect
the fulfill/revoke transactions, blocks, and the ERC-721 in a real block-explorer UI
(Anvil serves Otterscan's API natively; nothing is mocked). Teardown:
`containerlab destroy -t netlab/topology.clab.yml` + `just explorer-down` (the console's
chain is per-session; nothing else persists).

**Choosing the judgment mode.** With no `.env`, the two judgment slots run deterministic
stand-ins (instant, offline). To make them *real model judgments*, deploy the LLM once
and write `.env` (full steps: [`llmserve/README.md`](llmserve/README.md)):

```sh
uv run modal setup                                              # once per machine
uv run modal secret create a2a-llm-key LLM_API_KEY=$(openssl rand -hex 16)
uv run modal deploy llmserve/modal_llm.py                       # → your /v1 endpoint
cp .env.example .env                                            # fill in URL + token
```

Restart `just console` — the header pill turns `judgment · qwen3-4b`. **Click the pill**
to flip between live LLM and deterministic at any time (great for contrasting the two);
if the network dies, the console falls back deterministically on its own.

## Quickstart (development)

```sh
uv run pytest            # unit + lifecycle (mock) + chainmcp's live-Anvil cross-stack
                         #   tests (those skip unless `forge build` ran in contracts/)
SKELETON_PROFILE=chain \
  uv run pytest e2e/     # skeleton v1: the same lifecycle on a real local chain
just                     # list available recipes (incl. deploy-local)
```

Evidence for every completed milestone lives in [`docs/evidence/`](docs/evidence/) —
**evidence or it didn't happen.**
