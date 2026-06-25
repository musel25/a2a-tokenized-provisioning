# Recipes grow with the milestones; `just up` / `just down` arrive in Phase 6.

default:
    @just --list

# run all Python tests (mock profile)
test:
    uv run pytest

# ruff lint (rules + line-length live in pyproject.toml)
lint:
    uv run ruff check .

# ruff auto-format (rewrites files in place)
fmt:
    uv run ruff format .
