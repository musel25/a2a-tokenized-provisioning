# Recipes grow with the milestones; `just up` / `just down` arrive in Phase 6.

default:
    @just --list

# run all Python tests (mock profile)
test:
    uv run pytest

# lint
lint:
    uv run ruff check .

# format
fmt:
    uv run ruff format .
