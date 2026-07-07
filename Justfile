default:
    @just --list

# bring up the chain-only stack (Anvil → deploy → controller), block until healthy.
# The SR Linux lab is separate (containerlab deploy) + SKELETON_PROFILE=chain+net.
up:
    uv run python -m e2e.bringup

# stop whatever `up` started (reads e2e/runs/current.json); idempotent.
down:
    uv run python -m e2e.bringup down

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
