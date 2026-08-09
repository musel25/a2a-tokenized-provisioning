# llmserve — the agents' LLM, deployed on Modal

The agents never knew a backend (ADR-001): `agents.llm.LLMClient` speaks
OpenAI-compatible `/v1` at whatever `LLM_BASE_URL` says. This directory deploys that
endpoint for real — vLLM serving **Qwen3-4B** on a serverless Modal L4 GPU — so Ada's
accept/reject and Bell's quote are *actual model judgments* in the live console, at
interactive speed (the local box takes ~140 s/decision; this takes ~1–2 s warm).

## One-time setup

```sh
uv run --group llm modal setup        # browser auth (once per machine)
TOKEN=$(openssl rand -hex 16)
uv run --group llm modal secret create a2a-llm-key LLM_API_KEY=$TOKEN
```

`modal` sits in the `llm` dependency group, outside the default sync — hence `--group llm`
on every command here. Omit it on a workspace that has never synced the group and
`modal_llm.py` dies with `ModuleNotFoundError: No module named 'modal'`. That error means
*sync the group*; it has never meant the module's `import modal` is spurious (every
`@app.function` / `modal.Image` / `modal.Volume` in the file needs it).

## Deploy (and redeploy after edits)

```sh
uv run --group llm modal deploy llmserve/modal_llm.py
# → https://<workspace>--a2a-llm-serve.modal.run
```

First-ever boot downloads ~8 GB of weights into a Modal volume (a few minutes);
every later cold start loads from the volume (~60 s), then stays warm 15 min.

## Point the stack at it — `.env` in the repo root

```sh
LLM_BASE_URL=https://<workspace>--a2a-llm-serve.modal.run/v1
LLM_MODEL=qwen3-4b
LLM_API_KEY=<the same TOKEN>
A2A_LIVE_LLM=1
```

`just console` loads `.env` automatically. Delete `.env` (or unset `A2A_LIVE_LLM`)
to fall back to the deterministic stand-ins — the demo never *requires* the network.

## Smoke test

```sh
source .env && curl -s $LLM_BASE_URL/chat/completions \
  -H "Authorization: Bearer $LLM_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"qwen3-4b","messages":[{"role":"user","content":"say ok"}],"max_tokens":5}'
```

## Cost shape

Scale-to-zero when idle: you pay only while a container is up (~$0.80/hr for the L4,
against Modal's $30/mo free credits). A demo session ≈ warm window ≈ cents.
