"""Deploy Gemma 4 on a single GPU via Modal + vLLM (the CereMind speed baseline).

This stands up an OpenAI-compatible `/v1/chat/completions` endpoint serving the
open-weight **Gemma 4** on one GPU, so the "Cerebras vs Modal" tab can race the
*same model family* on real hardware instead of a simulated rate. Cerebras runs
Gemma 4 on wafer-scale silicon (~1800 tok/s); a single GPU here will land in the
tens-to-low-hundreds of tok/s - that delta is the whole demo.

--------------------------------------------------------------------------------
One-time setup
--------------------------------------------------------------------------------
1. pip install modal
2. modal token new                       # authenticate the CLI to your account
3. Store your Hugging Face token (Gemma is gated) as a Modal secret named
   "huggingface" with an HF_TOKEN key:

       modal secret create huggingface HF_TOKEN=hf_xxx

   (Use the same token that's in your .env's HUGGINGFACE_TOKEN.)

--------------------------------------------------------------------------------
Deploy
--------------------------------------------------------------------------------
    modal deploy scripts/modal_gemma_vllm.py

Modal prints a URL like:

    https://<workspace>--ceremind-gemma-baseline-serve.modal.run

Then point CereMind at it in .env (note the trailing /v1):

    BASELINE_BASE_URL=https://<workspace>--ceremind-gemma-baseline-serve.modal.run/v1
    BASELINE_MODEL=gemma-4-modal
    BASELINE_API_KEY=
    BASELINE_LABEL=Gemma 4 - Modal (H100, vLLM)

Smoke-test it without touching CereMind:

    modal run scripts/modal_gemma_vllm.py

--------------------------------------------------------------------------------
Knobs you may want to flip
--------------------------------------------------------------------------------
- GPU:    set GPU below (e.g. "H100", "H200", "A100-80GB"). H200 is fastest/priciest.
- MODEL:  MODEL_NAME defaults to the open-weight Gemma 4 (26B-A4B MoE). Swap to a
          dense variant if you have access and want a closer match to Cerebras' 31B.
- SPEED:  set SPECULATIVE=True to enable draft-model speculative decoding. It makes
          the GPU baseline *faster* (narrowing the gap) - leave it False for the
          plain single-GPU number, flip it on if a judge asks "is the GPU tuned?".
"""
from __future__ import annotations

import modal

# --- What to serve ---------------------------------------------------------- #
# The open-weight Gemma 4 variant (MoE: 26B total params, ~4B active per token).
MODEL_NAME = "google/gemma-4-26B-A4B-it"
MODEL_REVISION = "47b6801b24d15ff9bcd8c96dfaea0be9ed3a0301"  # pin for reproducibility
SERVED_NAME = "gemma-4-modal"  # what CereMind sends as BASELINE_MODEL

# --- Where to serve it ------------------------------------------------------ #
GPU = "H100"          # one GPU; try "H200" for the strongest (most honest) baseline
N_GPU = 1
VLLM_PORT = 8000
MINUTES = 60

# Disable both Torch compile + CUDA-graph capture for snappier cold starts.
# Set False if you keep a replica warm and want peak throughput.
FAST_BOOT = True
# Draft-model speculative decoding. Off = plain single-GPU rate (recommended for a
# clean, defensible baseline). On = a tuned, faster GPU number.
SPECULATIVE = False

vllm_image = (
    modal.Image.from_registry("nvidia/cuda:12.9.0-devel-ubuntu22.04", add_python="3.12")
    .entrypoint([])
    .uv_pip_install("vllm==0.21.0", "huggingface_hub[hf_transfer]")
    .env(
        {
            "HF_HUB_ENABLE_HF_TRANSFER": "1",  # faster weight downloads
            "VLLM_LOG_STATS_INTERVAL": "1",    # frequent throughput logging
        }
    )
)

# Cache weights + vLLM JIT artifacts across cold starts so we don't re-download.
hf_cache_vol = modal.Volume.from_name("huggingface-cache", create_if_missing=True)
vllm_cache_vol = modal.Volume.from_name("vllm-cache", create_if_missing=True)

app = modal.App("ceremind-gemma-baseline")


@app.function(
    image=vllm_image,
    gpu=f"{GPU}:{N_GPU}",
    secrets=[modal.Secret.from_name("huggingface")],
    scaledown_window=15 * MINUTES,  # stay warm a bit, then scale to zero (no idle cost)
    timeout=10 * MINUTES,           # allow time to pull weights on a cold start
    volumes={
        "/root/.cache/huggingface": hf_cache_vol,
        "/root/.cache/vllm": vllm_cache_vol,
    },
)
@modal.concurrent(max_inputs=32)
@modal.web_server(port=VLLM_PORT, startup_timeout=10 * MINUTES)
def serve():
    import json
    import subprocess

    cmd = [
        "vllm", "serve", MODEL_NAME,
        "--revision", MODEL_REVISION,
        "--served-model-name", SERVED_NAME, MODEL_NAME,
        "--host", "0.0.0.0",
        "--port", str(VLLM_PORT),
        "--tensor-parallel-size", str(N_GPU),
        "--gpu-memory-utilization", "0.90",
        "--uvicorn-log-level=info",
    ]

    # Text-only for the speed race -> frees VRAM for a bigger KV cache.
    cmd += ["--limit-mm-per-prompt", f"'{json.dumps({'image': 0, 'video': 0, 'audio': 0})}'"]

    # Parse Gemma 4 chain-of-thought into `reasoning_content` so the baseline runs
    # the same reason+answer workload as Cerebras (the client requests thinking).
    cmd += ["--reasoning-parser", "gemma4"]

    cmd += ["--enforce-eager"] if FAST_BOOT else ["--no-enforce-eager", "--async-scheduling"]

    if SPECULATIVE:
        spec = {
            "model": "google/gemma-4-26B-A4B-it-assistant",
            "revision": "f188f476dc11dd5bb3014dc861529d316bce49d3",
            "num_speculative_tokens": 4,
        }
        cmd += ["--speculative-config", f"'{json.dumps(spec)}'"]

    print("Launching:", " ".join(cmd))
    subprocess.Popen(" ".join(cmd), shell=True)


@app.local_entrypoint()
async def test(content: str = "In 3 sentences, why is fast LLM inference useful for incident response?"):
    """`modal run` this file to spin up a replica and fire one streamed request."""
    import json
    import urllib.request

    base = serve.get_web_url()
    print(f"Endpoint: {base}")
    print(f"Set BASELINE_BASE_URL={base}/v1  and  BASELINE_MODEL={SERVED_NAME}\n")

    payload = {
        "model": SERVED_NAME,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 256,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": True},
    }
    req = urllib.request.Request(
        f"{base}/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        data = json.loads(r.read())
    print(data["choices"][0]["message"]["content"])
    print("\nusage:", data.get("usage"))
