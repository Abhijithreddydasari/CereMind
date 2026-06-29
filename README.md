# CereMind

**An agentic, multimodal incident-response copilot powered by Gemma 4 31B on Cerebras.**

Generic RAG tells you *where to look*. CereMind does the looking **and** the fixing.
When a pipeline job fails, an autonomous **Incident Commander** agent triages the alert,
reads the attached dashboard/DAG snapshot with **Gemma 4 vision**, dispatches **specialist
sub-agents** that call real tools (logs, metrics, config history, runbooks), converges on a
**cited root cause**, and then **remediates behind a risk-tiered human approval gate** -
applying the fix and rerunning the job to green.

Because the whole multi-hop loop runs on Cerebras (~1850 tok/s for Gemma 4 31B), an
investigation that takes other AI-SRE tools *minutes* completes in **~10-15 seconds** - fast
enough to be a real-time, interactive war-room teammate instead of a batch job you check later.

> Built for the Cerebras x Google DeepMind Gemma 4 Hackathon.
> Primary track: **Enterprise Impact**. Secondary: **Multiverse Agents** (multi-agent + multimodal).

---

## Why this isn't "another RAG demo"

| | Generic multimodal RAG | CereMind |
|---|---|---|
| Output | A list of relevant docs | A cited root cause **and an applied fix** |
| Tools | Retrieval only | Real tools: logs, metrics, config diffs, **revert + rerun** |
| Agents | Single retrieve-then-answer | Commander + telemetry/change/knowledge specialists |
| Multimodal | Images embedded for search | Gemma 4 **vision reads the alert dashboard** to drive triage |
| Speed | Nice-to-have | The product: interactive RCA in seconds, not minutes |
| Safety | n/a | Read-only by default; writes gated by human approval + full audit log |

## What makes CereMind different

Most incident-AI projects - even strong multi-agent, multimodal, Cerebras-powered ones -
are **recommendation engines**: they triage, retrieve runbooks, and produce a *ranked action
plan*, then hand it to a human and stop. CereMind is the opposite: a **closed-loop operator**
that acts, proves the fix worked, and prevents the failure from ever recurring - under
enterprise governance.

> **They diagnose. CereMind resolves - and makes sure it never happens again.**
>
> Most tools fight the fire. CereMind also fireproofs the building.

### The "immune system" loop

```
Detect  ->  Diagnose  ->  Fix  ->  Verify  ->  (Rollback if not green)  ->  Immunize
(alert)    (cited RCA)  (apply)  (rerun =     (auto-revert + escalate)    (preventive
                                  green?)                                  guardrail)
```

### Differentiator scorecard

| Capability | Triage/recommendation tools | CereMind |
|---|---|---|
| Closed-loop **action** (apply fix) | No - outputs a plan | **Yes** - applies fix via real tools |
| **Verify** the fix worked | No | **Yes** - reruns and confirms green |
| **Auto-rollback** safety net | No | **Yes** - reverts itself + escalates if rerun isn't green |
| **Immunize** (prevent recurrence) | No | **Yes** - generates a preventive guardrail/policy + files it as a PR |
| **Hypothesis racing** (speed -> better decisions) | No | **Yes** - scores N candidate fixes in parallel, picks safest |
| **Business-impact meter** (MTTR + $) | Speed only | **Yes** - MTTR + downtime-cost avoided, per incident |
| **Multi-incident breadth** | n/a | **Yes** - 4 distinct failure classes (OOM, schema drift, dependency bump, vendor 429) |
| **Blast-radius** / downstream impact | No | Roadmap - downstream dependency + SLA impact map |
| Risk-tiered **approval gate** | n/a | **Yes** |
| Immutable **audit log** / post-mortem | Partial | **Yes** |
| **Sovereign self-host** (open-weight) | Usually SaaS-locked | **Yes** - Gemma + EmbeddingGemma, runs in-perimeter |
| Real orchestrator via **swappable adapter** | n/a | **Yes** - mock -> Airflow/CI |

(Yes = implemented today; Roadmap = not yet built.)

### Incident library (multi-incident breadth)

CereMind ships **four distinct data/CI-pipeline incident packs**, each with its own DAG snapshot,
logs, metrics, config history, runbooks, culprit, fix, and preventive guardrail - so the agent's
reasoning visibly differs per incident instead of replaying one script:

| Scenario | Failed stage | Root cause | Fix | Guardrail filed |
|---|---|---|---|---|
| Memory cut -> OOMKill | transform | cost-bot cut `worker_memory_mb` 8192->2048 | revert change + rerun | block memory cuts below floor |
| Schema / data-contract drift | transform | source v2 renamed `customer_id`->`cust_id` | revert source change + rerun | schema-contract check in CI |
| Dependency / image bump | transform | pyarrow 14->17 removed an API | revert image pin + rerun | gate bumps behind a canary |
| Vendor rate-limit (HTTP 429) | ingest | concurrency 4->32 exceeded the contract | revert concurrency + rerun | per-vendor concurrency budget |

Pick a scenario in the War Room before firing the alert.

### Flagship feature - Immunize (preventive guardrail generation)

After an incident is resolved, CereMind generates a **guardrail that makes the entire class
of failure impossible to recur**, and files it (PR/ticket). For the OOM scenario it proposes,
e.g., a CI policy: *"block any config change that sets `transform.worker_memory_mb` below 4096;
require SRE review for memory-affecting changes."* Each incident leaves the system permanently
more reliable - reactive firefighting becomes compounding prevention. No triage-only tool can
do this, because prevention requires an agent that already understands and acts on the fix.

### The demo standouts (now implemented)

1. **Immunize** - the flagship preventive-guardrail step above (a "Prevention" card + filed PR artifact).
2. **Verify + auto-rollback** - if the rerun isn't green, CereMind reverts its own change and
   escalates (ticket + Slack). Autonomy *with* a seatbelt - the thing that makes "let the AI act"
   enterprise-credible.
3. **Hypothesis racing** - because Cerebras is fast, CereMind evaluates multiple candidate fixes
   (rerun-as-is / override / revert) **in parallel** (`asyncio.gather` over Cerebras calls), scores
   each with a predicted outcome, and picks the safest. Turns raw token speed into **decision
   quality**, the strongest justification for *why Cerebras specifically*. A plain rerun scores low
   because the injected failures are deterministic.
4. **Business-impact meter** - MTTR + dollars-of-downtime-avoided (per-scenario `$ / min` vs a
   human-MTTR baseline), surfaced on resolution. Makes Track 3 impact tangible.

Still on the roadmap: a **blast-radius map** (downstream dependency/SLA impact).

## Architecture

```
Alert (job-failed webhook, carries a DAG snapshot)
        |
        v
Incident Commander  --- vision (Gemma 4) reads the snapshot
        |  triage plan
        v
 Specialist sub-agents (each = bounded ReAct loop, own tools)
   - telemetry : get_job_runs / get_job_logs / get_metrics
   - change    : list_recent_config_changes / config_diff
   - knowledge : query_runbook / find_similar_failures  (EmbeddingGemma + Qdrant)
        |  findings + observations
        v
 Synthesis -> structured, cited Root Cause
        |
        v
 Hypothesis racing -> score N candidate fixes in parallel (Cerebras), pick safest
        |
        v
 [ Tier 2 high-risk? ] --yes--> Human approval gate --approve--> apply fix
        |                                                          |
        no (auto)                                                  v
        +--------------------------------------------> revert_config -> rerun_job
                                                                   |
                                            verify green? --no--> auto-rollback + escalate
                                                   |
                                                  yes -> summary (MTTR + $) -> Immunize (file guardrail PR) -> audit log
```

Everything runs in **one Cloud Run container** (FastAPI serving a React SPA). Gemma 4 runs on
Cerebras (external API). The investigated pipeline sits behind a swappable `PipelineAdapter`.

## Tech stack

- **Backend:** Python 3.11, FastAPI, SSE streaming. `gemma-4-31b` on Cerebras via the
  OpenAI-compatible Chat Completions API (vision + strict tool calling + `reasoning_effort`).
- **Retrieval:** EmbeddingGemma (`google/embeddinggemma-300m`) + Qdrant, with **permission-aware
  (namespace/ACL) filtering**. Degrades gracefully to a generic ST model, then a hashing
  vectorizer, so it always runs.
- **Frontend:** React + Vite + TypeScript + Tailwind - a live "war-room" console.
- **Deploy:** single multi-stage container on Google Cloud Run; Cerebras key in Secret Manager.

## Run it locally

Runs fully **offline with a built-in simulated agent** if you have no API key, so you can see
the entire UX immediately. Add a Cerebras key for real ultra-fast inference.

### 1. Backend

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt

cp .env.example .env          # optional: add CEREBRAS_API_KEY for the real model

cd backend
uvicorn app.main:app --reload --port 8090
```

### 2. Frontend (dev)

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173  (proxies /api to :8090)
```

For a production-style single-server run, `npm run build` outputs into `backend/app/static`,
and the backend then serves the SPA at `http://localhost:8090/`.

### 3. Try it

- Open the app, **pick a scenario** (OOM, schema drift, dependency bump, or vendor 429), click
  **Simulate job-failed alert**, and watch the live investigation, the parallel **hypothesis race**,
  and the cited root cause.
- When it reaches the gate, click **Approve & apply fix** to let CereMind apply the fix and rerun
  the job to green - then it files a preventive **guardrail PR** (Immunize) and shows MTTR + dollars
  avoided. If a rerun doesn't go green, it **auto-rolls-back** its own change and escalates.
- Open the **Cerebras vs Modal** tab and run the same Gemma 4 prompt on both engines
  (live tokens/sec, time-to-first-token, and the speedup multiple).

## Verify the real Cerebras path

```bash
cd backend
python smoke_cerebras.py     # checks chat, strict tool calling + reasoning_effort, and vision
python smoke_test.py         # full offline end-to-end agent + RAG + remediation test
```

## Speed proof: race Cerebras vs the same model on a GPU (Modal)

The **Cerebras vs Modal** tab runs the *identical* Gemma 4 prompt on two backends
side by side and reports live **tokens/sec**, **time-to-first-token**, and the
resulting **speedup** - the headline "why Cerebras" number. Cerebras serves Gemma 4
on wafer-scale silicon (~1800 tok/s); a single GPU lands in the tens-to-low-hundreds
of tok/s. To make it a *real* side-by-side (not a simulated rate), stand up the
open-weight Gemma 4 on one GPU via Modal:

```bash
pip install modal
modal token new                                   # authenticate the CLI
modal secret create huggingface HF_TOKEN=hf_xxx   # Gemma is gated (reuse HUGGINGFACE_TOKEN)
modal deploy scripts/modal_gemma_vllm.py          # prints an endpoint URL
```

Then set these in `.env` (note the trailing `/v1`) and restart the backend:

```bash
BASELINE_BASE_URL=https://<workspace>--ceremind-gemma-baseline-serve.modal.run/v1
BASELINE_MODEL=gemma-4-modal
BASELINE_LABEL=Gemma 4 - Modal (H100, vLLM)
```

The script is parameterized (GPU tier, model variant, speculative decoding) - see its
header. The first request after a scale-to-zero cold start pays a one-time warm-up; hit
**Run** once before the demo so the live race is instant. With `BASELINE_*` unset, the
pane gracefully falls back to a clearly-labeled simulated rate.

## Configuration (`.env`)

| Variable | Purpose |
|---|---|
| `CEREBRAS_API_KEY` | Enables real Gemma 4 on Cerebras. Unset = simulated agent. |
| `CEREBRAS_MODEL` | Defaults to `gemma-4-31b`. |
| `FORCE_SIMULATED` | `true` forces the deterministic simulated agent even with a key set (offline/deterministic demos & tests). |
| `BASELINE_BASE_URL` / `BASELINE_MODEL` / `BASELINE_API_KEY` | OpenAI-compatible GPU endpoint for the speed race (e.g. Gemma 4 on Modal via `scripts/modal_gemma_vllm.py`). Unset = simulated baseline at `BASELINE_SIM_TPS`. |
| `BASELINE_LABEL` | Display name for the baseline pane (e.g. `Gemma 4 - Modal (H100, vLLM)`). |
| `EMBEDDING_BACKEND` | `auto` (EmbeddingGemma if installed, else ST, else hashing) / `embeddinggemma` / `hashing`. |
| `HUGGINGFACE_TOKEN` | For pulling gated EmbeddingGemma weights. |
| `PIPELINE_BACKEND` | `mock` (default) or `airflow`. |

## Deploy to Google Cloud Run

```bash
PROJECT_ID=your-proj REGION=us-central1 CEREBRAS_API_KEY=csk-... \
  ./scripts/deploy_cloudrun.sh
```

This enables the needed APIs, stores the Cerebras key in **Secret Manager**, builds the
container with Cloud Build, deploys to Cloud Run (scale-to-zero), and smoke-tests `/api/health`.

## Production readiness (implemented vs. roadmap)

**Implemented now (lean but real):**
- Stateless container -> Cloud Run horizontal autoscale + scale-to-zero.
- Secrets via Secret Manager (no keys in code/images).
- **Permission-aware retrieval** - chunks carry an ACL namespace; queries filter to the caller's
  allowed namespaces (the demo proves a `finance`-only doc is never retrieved).
- **Read-only by default**; mutating actions are gated behind a human approval tier.
- **Append-only audit log** of every thought, tool call, observation, approval, and execution.

**Documented extensions (the seams are already in the code):**
- Swap the `PipelineAdapter` from `mock` to a real orchestrator. An `airflow` backend stub maps
  the same interface onto Apache Airflow's REST API (local docker-compose; **not** Cloud
  Composer). The same seam fits CI systems (GitHub Actions) or Datadog/Prometheus for telemetry.
- Managed Qdrant / Vertex AI Vector Search; VPC-SC + CMEK; per-tenant isolation; Cloud
  Trace/Logging.
- **Sovereign / self-hosted:** because Gemma 4 and EmbeddingGemma are open-weight, the entire
  stack can run inside a customer's perimeter with no data egress - a path Amazon Q and other
  SaaS-locked tools structurally cannot offer.

## Repository layout

```
backend/app/
  agents/      commander (orchestrator) + specialists + prompts + schemas
  llm/         cerebras_client (real + simulated), baseline_client
  tools/       telemetry / changes / knowledge / remediation + registry (strict schemas, risk tiers)
  rag/         embeddings (EmbeddingGemma) + vectorstore (Qdrant) + ingest (corpus)
  pipeline/    scenarios (4 incident packs) + adapter + mock_backend + airflow_backend + gen_snapshot
  api/         routes_incident (webhook/start/SSE) + routes_actions (approval) + routes_speed
  audit/       append-only audit log
frontend/src/  IncidentConsole, AgentTimeline, RootCauseCard, RemediationPanel, SpeedCompare, ScreenshotDrop
docker/        multi-stage Dockerfile
scripts/       deploy_cloudrun.sh
```

## Notes & honesty

- With no `CEREBRAS_API_KEY`, the agent is a deterministic **simulation** so the UX is fully
  demoable offline; the orchestration code path is identical to the real one.
- The GPU baseline in the speed tab is labeled **representative** until you set
  `BASELINE_*`; with a real endpoint (e.g. Gemma 4 on Modal) it streams the *same model*
  from actual hardware for a true side-by-side, and tokens/sec uses the provider's exact
  `completion_tokens` (not a chunk-count estimate).
