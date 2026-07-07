"""The agents' LLM, deployed (ADR-001 amendment): vLLM on a Modal L4 GPU.

Serves Qwen3-4B — the same model family as the local-Ollama canon — behind vLLM's
OpenAI-compatible /v1, which is the ONLY interface the agents know (rule: no
backend-specific SDK; `agents.llm.LLMClient` just points at LLM_BASE_URL). Deploying
this changes three env vars and zero lines of agent code.

    uv run modal deploy llmserve/modal_llm.py
    # → https://musel25--a2a-llm-serve.modal.run/v1

Auth: vLLM requires the bearer token in the Modal secret `a2a-llm-key` (create once:
`modal secret create a2a-llm-key LLM_API_KEY=<token>`); clients send the same token
as LLM_API_KEY. Cost shape: scale-to-zero when idle, ~60 s cold start on the first
request (weights load from a Modal volume), then stays warm 15 min past the last call.
"""

import subprocess

import modal

MODEL = "Qwen/Qwen3-4B-Instruct-2507"  # ungated; instruct (no <think> preamble)
SERVED_AS = "qwen3-4b"  # what clients put in LLM_MODEL
MINUTES = 60

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("vllm==0.9.1", "huggingface_hub[hf_transfer]==0.32.4")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})  # weights download in ~1 min, not ~10
)

# Weights persist across cold starts; only the FIRST boot ever downloads from HF.
# The torch.compile cache persists too — without it every cold start pays ~3 min of
# graph recompilation (measured on the first boot); with it, ~60 s.
weights = modal.Volume.from_name("a2a-llm-weights", create_if_missing=True)
compile_cache = modal.Volume.from_name("a2a-llm-compile-cache", create_if_missing=True)

app = modal.App("a2a-llm")


@app.function(
    image=image,
    gpu="L4",  # 24 GB — a 4B model in bf16 leaves plenty of KV cache
    volumes={"/root/.cache/huggingface": weights, "/root/.cache/vllm": compile_cache},
    secrets=[modal.Secret.from_name("a2a-llm-key")],
    scaledown_window=15 * MINUTES,  # stays warm through a demo, scales to zero after
    timeout=20 * MINUTES,
)
@modal.concurrent(max_inputs=32)
@modal.web_server(port=8000, startup_timeout=10 * MINUTES)
def serve() -> None:
    import os

    subprocess.Popen(
        [
            "vllm",
            "serve",
            MODEL,
            "--host", "0.0.0.0",
            "--port", "8000",
            "--served-model-name", SERVED_AS,
            "--api-key", os.environ["LLM_API_KEY"],
            "--max-model-len", "8192",  # decisions are short; smaller KV = faster boot
        ]
    )
