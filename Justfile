# .env (gitignored) carries LLM_BASE_URL/LLM_MODEL/LLM_API_KEY/A2A_LIVE_LLM — the
# deployed-LLM switch (llmserve/README.md). Absent .env = deterministic stand-ins.
set dotenv-load := true

default:
    @just --list

# bring up the chain-only stack (Anvil → deploy → controller), block until healthy.
# The SR Linux lab is separate (containerlab deploy) + SKELETON_PROFILE=chain+net.
up:
    uv run python -m e2e.bringup

# stop whatever `up` started (reads e2e/runs/current.json); idempotent.
down:
    uv run python -m e2e.bringup down

# block explorer over the console's chain → http://localhost:5100
# Otterscan is browser-side: the page you open reads Anvil's ots_ API at 127.0.0.1:8545
# directly (the console pins its Anvil there when free). Start before or after the
# console — the tx hashes in the event stream become links once both are up.
explorer:
    docker rm -f a2a-otterscan 2>/dev/null || true
    docker run -d --name a2a-otterscan -p 5100:80 \
      -e ERIGON_URL=http://127.0.0.1:8545 otterscan/otterscan:latest
    @echo "explorer → http://localhost:5100"

explorer-down:
    docker rm -f a2a-otterscan

# the interactive operator console → http://127.0.0.1:8099
# Click "Ada, get me this" to drive the real pipeline (agents → chain → controller →
# router) and watch it in the trust relay. Bring the SR Linux lab up first for live
# enforcement: containerlab deploy -t netlab/topology.clab.yml
console:
    uv run --group demo python -m e2e.dashboard.server

# run all Python tests (mock profile)
test:
    uv run pytest

# ruff lint (rules + line-length live in pyproject.toml)
lint:
    uv run ruff check .

# ruff auto-format (rewrites files in place)
fmt:
    uv run ruff format .

# deploy MockTOK + A2ASettlement to a running Anvil → contracts/deployments/anvil.json.
# The key is anvil's well-known dev account #0 — a public constant, not a secret
# (real key custody starts at chainmcp, M1.5; CLAUDE.md rule 2 is about real keys).
deploy-local:
    @cast chain-id --rpc-url http://127.0.0.1:8545 > /dev/null 2>&1 || \
      (echo "no Anvil on :8545 — start one first, e.g.: anvil --timestamp 1757944500" && exit 1)
    cd contracts && forge script script/Deploy.s.sol --rpc-url http://127.0.0.1:8545 \
      --broadcast --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
    @echo "--- contracts/deployments/anvil.json ---" && cat contracts/deployments/anvil.json
