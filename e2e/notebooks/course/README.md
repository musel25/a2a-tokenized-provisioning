# The course — the whole repo, from absolute zero, by poking it

Fifteen notebooks that assume **no prior knowledge** — not of Python's typing machinery,
not of blockchains, not of routers — and build up, module by real module, to the full
worked example (Ada buys 50 Mbps from Bell for 10 TOK, one atomic transaction mints
ticket #7, a deterministic controller honors it, and Bell's on-chain revocation kills the
session mid-window) — and then past it, into the **feasibility evaluation**: how the
architecture was measured on a testbed as close to the real deal as a lab allows, what
the numbers say, and what they honestly don't.

Every cell runs against the **real repo code** (imports, `inspect.getsource`, live
objects) — never a simplified copy. Toy snippets appear only to introduce a language
construct before you meet the repo's real use of it. And every explanation block carries
an embedded **✏️ Your turn** exercise — a scaffolded cell you edit right where the
concept lands, with a fold-out solution — so you are doing, not just reading, the whole
way through.

## How to run

```bash
uv sync --all-packages          # once
forge build --root contracts    # once — enables the chain notebooks (06, 07, 11, 12)
```

Open any notebook in VS Code or Jupyter, pick the `.venv` kernel, run top to bottom.
Every notebook is **self-contained** (own imports, own disposable chain if it needs one)
and runs green headless with no lab and no LLM endpoint — cells that would need more
infrastructure detect its absence, tell you what to start, and skip.

Headless check (what CI-style verification looks like):

```bash
uv run --group demo jupyter nbconvert --to notebook --execute --stdout \
    e2e/notebooks/course/00_orientation.ipynb > /dev/null
```

## The path

| # | Notebook | You come out able to… | Extra infra |
|---|---|---|---|
| 00 | 🗺️ `00_orientation.ipynb` | retell the story, navigate the repo, run cells, explain what a module/import/trust domain is | — |
| 01 | 🧰 `01_python_toolbox.ipynb` | read every language construct the repo uses: type hints, `Annotated`, decorators, dataclasses, Enums, exceptions, `with`, threads | — |
| 02 | 🧬 `02_pydantic_from_zero.ipynb` | explain how every cross-package shape validates itself at the border — frozen models, constrained fields, discriminated unions, JSON round-trips | — |
| 03 | 🔌 `03_protocols_and_ports.ipynb` | write a class that satisfies a `Protocol` without inheriting, and say why the whole architecture swaps on that trick | — |
| 04 | 🎭 `04_the_canonical_example.ipynb` | dissect every canonical value (addresses, unix windows, integer money, the ABI blob — by hand) | — |
| 05 | 🎬 `05_the_walking_skeleton.ipynb` | run the entire lifecycle on cardboard fakes and name every check in the naive predicate | — |
| 06 | ⛓️ `06_blockchain_from_zero.ipynb` | derive an address from a key, drive a disposable chain with web3.py, and read `Settlement.sol` section by section | Anvil |
| 07 | 🖋️ `07_chainmcp_the_signing_adapter.ipynb` | sign an EIP-712 offer in Python that the Solidity contract accepts, and prove the digests match byte-for-byte | Anvil |
| 08 | 🕴️ `08_controller_the_bouncer.ipynb` | walk the real predicate's every deny path, defeat a replay attack, and drive the HTTP API in-process | — |
| 09 | 🛠️ `09_netctl_the_hands.ipynb` | explain gNMI/YANG paths, drive the mock provisioner, and read the real one honestly (ADR-006) | (lab optional) |
| 10 | 🤖 `10_agents_the_brains.ipynb` | run the LangGraph agents on a stub LLM and point at the exactly-two cells where judgment lives | — |
| 11 | 🌍 `11_worlds_and_profiles.ipynb` | swap the fake chain for the real one under an unchanged lifecycle — the composition root, live | Anvil |
| 12 | 🎆 `12_grand_finale.ipynb` | perform the whole play at maximum headless realism, including the revocation showpiece — then sit the integration exam | Anvil |
| 13 | 📏 `13_the_evaluation.ipynb` | explain how the architecture's feasibility was measured: the seven experiments as skeptic's questions, the two definitions of "enforced", the five simulation boundaries, the harness — and reproduce the predicate experiment live | — |
| 14 | 🧾 `14_results_and_conclusions.ipynb` | compute every headline number from the committed dataset (latency, nanosecond predicate, revocation lag, gas→dollars, adversarial matrix, LLM accuracy, trustlessness overhead), attach its honest boundary, and derive the feasibility verdict | — |

Read them **in order** the first time: each assumes everything before it and nothing after.
The arc is deliberate: **00–05** the language and the cardboard architecture, **06–10**
each real organ, **11–12** everything composed and performed, **13–14** the performance
measured — evaluation, results, conclusions.

## How this relates to the other learning surfaces

This course is the **from-zero spine**. The repo has three other hands-on surfaces, and
the intended rhythm is *watch → poke → touch the real thing*:

1. **This course** (`course/`) — progressive, beginner-glossed, narrative, exercise-driven.
   Start here.
2. **The explore notebooks** (`e2e/notebooks/*_explore.ipynb`) — compact per-component
   guided tours written at working-engineer altitude. Each course chapter links its twin
   as the "deeper dive"; `netctl_explore` and `console_explore` also cover the parts that
   need the live containerlab lab, and `evaluation_explore` renders the full five-figure
   set behind chapter 14.
3. **The scratch bench** (`e2e/notebooks/scratch_inspect.ipynb`) — pre-wired imports,
   playground-empty. Your own questions go there.
4. **The cast labs** (`contracts/EXPLORE*.md`) — the Solidity surface, driven from a
   terminal against a live Anvil (`forge inspect`, `cast send/call`).

For the reading route through the docs (specs, ADRs, evaluation report), follow
[`docs/LEARNING-PATH.md`](../../../docs/LEARNING-PATH.md) — this course is its
executable companion.
