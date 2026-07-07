# 05 — Rebuilding this repo from scratch

A command-by-command recipe for reconstructing the repository skeleton: the uv
workspace (Python) and the Foundry project (Solidity). This is the "what would I
type into an empty directory to get here" reference.

> Scope: this builds the **plumbing** — the workspace, the member packages, the
> Foundry project, the toolchain pins. It does *not* write the feature code (the
> models, the contract, the controller). Those arrive milestone by milestone via
> `docs/01-implementation-plan.md`.

---

## The one idea to hold first: two toolchains, not one

This repo is governed by **two independent package managers**, and conflating
them is the most common mistake:

| Toolchain | Owns | Manifest | Lockfile | Installs deps with |
|---|---|---|---|---|
| **uv** | all Python (`interfaces`, `e2e`, `controller`, `chainmcp`, `agents`, `netctl`) | `pyproject.toml` | `uv.lock` | `uv add <pkg>` |
| **Foundry** | all Solidity (`contracts/`) | `foundry.toml` | `foundry.lock` | `forge install <gh-org/repo>` (git submodules) |

Consequences that correct the obvious wrong guesses:

- **Foundry is *not* a `uv add`.** `forge` / `cast` / `anvil` are a standalone
  binary toolchain installed via `foundryup`. uv never sees them.
- **`contracts/` is *not* a uv workspace member.** It has no `pyproject.toml`. It
  is deliberately absent from `[tool.uv.workspace] members`. Solidity
  dependencies (forge-std, OpenZeppelin) are installed by `forge install` as
  **git submodules** under `contracts/lib/`, never by uv.
- A Solidity library like OpenZeppelin is added with `forge install`, **not**
  `uv add` — there is no Python involved.

So the mental order is: set up the git repo → build the uv workspace → add the
Foundry project beside it. Two parallel tracks that only meet at the git root.

---

## Prerequisites (install once, machine-wide)

```bash
# uv — Python package & workspace manager
curl -LsSf https://astral.sh/uv/install.sh | sh

# Foundry — forge / cast / anvil
curl -L https://foundry.paradigm.xyz | bash
foundryup            # downloads/updates the actual binaries

# (optional) just — the task runner used by the Justfile
#   on Debian/Ubuntu: sudo apt install just   — or: cargo install just
```

Verify:

```bash
uv --version
forge --version
```

---

## Step 0 — Git repo

Per the global workflow, the repo exists before any code. With the `gh` CLI:

```bash
gh repo create a2a-tokenized-provisioning --public \
  --description "Agent-to-agent tokenized network-service provisioning" --clone
cd a2a-tokenized-provisioning
# (or: mkdir … && cd … && git init  if creating the remote later)
```

---

## Step 1 — The uv workspace root

The root `pyproject.toml` is a **workspace coordinator**, not a real package: it
ships no code, declares no runtime dependencies, and only lists its members plus
the shared dev/demo tool groups.

```bash
# Scaffold a minimal project, then we trim it into a workspace root.
uv init --bare        # creates a dependency-free pyproject.toml, no sample code
```

Then edit the root `pyproject.toml` by hand to match this repo. The
workspace-defining pieces are:

```toml
[project]
name = "a2a-provisioning"
version = "0.0.0"
description = "Agent-to-agent tokenized network-service provisioning (workspace root)"
requires-python = ">=3.12"
dependencies = []                      # the root ships nothing

[tool.uv.workspace]
members = ["interfaces", "e2e"]        # grows as packages land; contracts is NOT here

[dependency-groups]                    # dev tooling, shared across the workspace
demo = ["ipykernel>=7.3.0", "nbconvert>=7.17.1"]
dev  = ["pytest>=8.0", "ruff>=0.4"]

[tool.pytest.ini_options]
testpaths = ["interfaces/tests", "e2e/tests"]

[tool.ruff]
line-length = 100
src = ["interfaces/src", "e2e/src"]
extend-exclude = ["e2e/notebooks"]     # teaching notebooks aren't library code
```

> `members` is a list, not magic discovery: a package only joins the workspace
> once its directory is named here (or matches a glob). Today it's
> `interfaces` + `e2e`; the other Python packages get appended as their
> milestones arrive.

Install the shared dev tools into the workspace virtualenv:

```bash
uv add --dev pytest ruff
uv add --group demo ipykernel nbconvert
```

This creates the single shared `.venv/` at the root and writes `uv.lock`. Every
member shares this one environment and lockfile.

---

## Step 2 — The first member: `interfaces`

`interfaces` is the published language — the pydantic shapes and Protocol ports
every other package imports. It's a real, buildable library (src layout,
hatchling backend).

```bash
uv init --lib interfaces        # src/interfaces + hatchling build-system + pyproject
```

`uv init --lib` gives you a `src/<name>` package. This repo renames the import
package to `a2a_interfaces` (the distribution stays `a2a-interfaces`), so adjust
the layout and the wheel target:

```bash
# rename the generated package dir to the real import name
mv interfaces/src/interfaces interfaces/src/a2a_interfaces
```

`interfaces/pyproject.toml` should end up as:

```toml
[project]
name = "a2a-interfaces"
version = "0.0.0"
description = "Published language: cross-package shapes and ports (see docs/03-interfaces.md)"
requires-python = ">=3.12"
dependencies = ["pydantic>=2.7"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/a2a_interfaces"]      # tell hatchling where the import package lives
```

Add its one runtime dependency **scoped to this member** — this is the
`--package` flag you were reaching for:

```bash
uv add --package a2a-interfaces pydantic
```

`--package <distribution-name>` writes the dependency into *that member's*
`pyproject.toml`, not the root's. (`uv add pydantic` from the root with no
`--package` would put it on the root coordinator — wrong.)

---

## Step 3 — The second member: `e2e` (and a cross-member dependency)

`e2e` is the stage: skeleton, lifecycle tests, bring-up. It depends on
`interfaces`, which demonstrates how one workspace member depends on another.

```bash
uv init --lib e2e
mv e2e/src/e2e e2e/src/e2e        # (already correct here; package name == import name)

# add the intra-workspace dependency:
uv add --package a2a-e2e a2a-interfaces
```

Because `a2a-interfaces` is itself a workspace member, uv records it as a
**workspace source** rather than fetching from PyPI. The result in
`e2e/pyproject.toml`:

```toml
[project]
dependencies = ["a2a-interfaces"]

[tool.uv.sources]                       # uv adds this automatically
a2a-interfaces = { workspace = true }   # resolve from the local workspace, not PyPI
```

Then add `e2e` to the root's `members` list (Step 1) if it isn't already, and
re-sync:

```bash
uv sync
```

> **Adding any future Python package** (`controller`, `chainmcp`, …) is this same
> three-move pattern: `uv init --lib <dir>` → append the dir to root
> `members` → `uv add --package <name> <deps>`.

---

## Step 4 — The Foundry project: `contracts/`

Separate track. Nothing below touches uv.

`forge init` scaffolds a Foundry project (`src/`, `test/`, `script/`,
`foundry.toml`, and `lib/forge-std` as a submodule). Because we're inside an
existing git repo, suppress its git/commit behavior:

```bash
forge init --no-commit contracts        # scaffold into ./contracts without committing
```

This already installs **forge-std** as a git submodule (recorded in
`.gitmodules` + `foundry.lock`). Add any further Solidity libraries the same way
— for example OpenZeppelin (used for ERC-721 later):

```bash
cd contracts
forge install OpenZeppelin/openzeppelin-contracts
cd ..
```

> `forge install <org/repo>` clones the dependency into `contracts/lib/<name>`
> and registers it as a **git submodule**. This is why `contracts/lib/` is *not*
> gitignored — the submodule pointers are tracked, the build output isn't.

Pin the compiler (a hard rule from `CLAUDE.md`: same solc everywhere, forever).
Edit `contracts/foundry.toml`:

```toml
[profile.default]
src  = "src"
out  = "out"
libs = ["lib"]
solc = "0.8.30"        # pinned: identical compiler in CI and on every machine
# M1.2: lets Solidity import OZ as `@openzeppelin/contracts/…` (its source lives one dir deeper)
remappings = ["@openzeppelin/contracts/=lib/openzeppelin-contracts/contracts/"]
```

Build and test to confirm the toolchain works:

```bash
cd contracts
forge build
forge test
cd ..
```

---

## Step 5 — Ignore rules

Two `.gitignore` files, because the build outputs differ per toolchain.

**Root `.gitignore`** — Python caches + Foundry's generated output (note:
`contracts/lib/` is deliberately *not* ignored, since forge-std is a tracked
submodule):

```gitignore
# Python
__pycache__/
*.py[cod]
.venv/
.pytest_cache/
.ruff_cache/
*.egg-info/

# Foundry generated output (lib/ is a tracked submodule — do NOT ignore it)
contracts/cache/
contracts/out/
contracts/broadcast/

# Notebooks: the .ipynb is tracked; these are caches
.ipynb_checkpoints/

# Local env / runs
.env
e2e/runs/
```

(`forge init` also drops a `contracts/.gitignore`; the root rules above are the
authoritative ones for this repo.)

---

## Step 6 — The task runner (optional but used here)

A root `Justfile` wraps the everyday commands so they're discoverable:

```just
default:
    @just --list

test:
    uv run pytest          # all Python tests, shared workspace venv

lint:
    uv run ruff check .

fmt:
    uv run ruff format .
```

---

## Step 7 — Plumbing added by later milestones (the log continues)

Each entry is the same pattern as the steps above; only the *reason* is new.

**M1.4 — the deploy artifact.**
- `foundry.toml` gains `fs_permissions = [{ access = "read-write", path = "./deployments" }]`
  — the deploy script writes `contracts/deployments/anvil.json`, and Foundry denies all
  fs access it wasn't granted (it also refuses paths above its own root, which is why
  the artifact lives *inside* contracts/).
- The Justfile gains `deploy-local` (expects a running Anvil, runs
  `forge script script/Deploy.s.sol`, prints the artifact).
- `.gitignore` gains `deployments/` — the artifact is machine-local, regenerate at will.

**M1.5 — the third member: `chainmcp` (and CI learns Foundry).**
- `chainmcp/pyproject.toml` exactly follows Step 3's cross-member pattern, adding
  `web3>=7.6` as its one external dependency; root `members` gains `"chainmcp"`, root
  `testpaths`/`ruff src` gain its paths.
- `.github/workflows/ci.yml`'s **python** job gains `foundry-rs/foundry-toolchain@v1` +
  `forge build --root contracts` *before* `uv run pytest`: chainmcp's cross-stack
  signature tests spawn a live `anvil` and load forge-built ABIs — without Foundry those
  tests skip, and the one seam nothing else can catch would go unwatched in CI.

**Post-plan — the deployed LLM (`llmserve/`, ADR-001 amendment).**
- Root gains a `llm` dependency group (`uv add --group llm modal`) — Modal is deploy
  tooling, not a runtime dependency of any package.
- One-time: `uv run modal setup` (browser auth), then
  `uv run modal secret create a2a-llm-key LLM_API_KEY=$(openssl rand -hex 16)`.
- `uv run modal deploy llmserve/modal_llm.py` → an OpenAI-compatible vLLM at
  `https://<workspace>--a2a-llm-serve.modal.run/v1` (Qwen3-4B on an L4; weights and the
  torch.compile cache live in Modal volumes so cold starts are ~60 s, not ~5 min).
- The Justfile gains `set dotenv-load := true`; a gitignored `.env` (template:
  `.env.example`) carries `LLM_BASE_URL`/`LLM_MODEL`/`LLM_API_KEY` + `A2A_LIVE_LLM=1`.
  No `.env` → the console's deterministic stand-ins; nothing else changes.

---

## Verify the whole skeleton

```bash
uv sync                    # resolve + install the entire workspace
uv run pytest              # Python tests across all members
cd contracts && forge test && cd ..   # Solidity tests
```

If both test runs pass, the two-toolchain skeleton is faithfully reconstructed.

---

## Cheat sheet — the commands, in order

```bash
# --- prerequisites (once per machine) ---
curl -LsSf https://astral.sh/uv/install.sh | sh
curl -L https://foundry.paradigm.xyz | bash && foundryup

# --- 0. repo ---
gh repo create a2a-tokenized-provisioning --public --clone && cd a2a-tokenized-provisioning

# --- 1. uv workspace root ---
uv init --bare
#   …edit pyproject.toml: add [tool.uv.workspace] members=["interfaces","e2e"]
uv add --dev pytest ruff
uv add --group demo ipykernel nbconvert

# --- 2. interfaces member ---
uv init --lib interfaces
mv interfaces/src/interfaces interfaces/src/a2a_interfaces
#   …edit interfaces/pyproject.toml: name=a2a-interfaces, wheel target=src/a2a_interfaces
uv add --package a2a-interfaces pydantic

# --- 3. e2e member (+ cross-member dep) ---
uv init --lib e2e
uv add --package a2a-e2e a2a-interfaces      # recorded as workspace source
uv sync

# --- 4. Foundry contracts (separate toolchain) ---
forge init --no-commit contracts
cd contracts && forge install OpenZeppelin/openzeppelin-contracts
#   …edit foundry.toml: solc = "0.8.30" + remappings for @openzeppelin/contracts/
forge build && forge test && cd ..

# --- 5. verify ---
uv run pytest
cd contracts && forge test && cd ..
```
