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
 Synthesis -> structured, cited Root Cause + proposed actions (risk-tiered)
        |
        v
 [ Tier 2 high-risk? ] --yes--> Human approval gate --approve--> apply fix
        |                                                          |
        no (auto)                                                  v
        +--------------------------------------------> revert_config -> rerun_job
                                                                   |
                                                          verify green -> summary + audit log
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

- Open the app, click **Simulate job-failed alert**, and watch the live investigation.
- When it reaches the gate, click **Approve & apply fix** to let CereMind revert the config and
  rerun the job to green.
- Open the **Cerebras vs GPU** tab and run the same prompt on both engines.

## Verify the real Cerebras path

```bash
cd backend
python smoke_cerebras.py     # checks chat, strict tool calling + reasoning_effort, and vision
python smoke_test.py         # full offline end-to-end agent + RAG + remediation test
```

## Configuration (`.env`)

| Variable | Purpose |
|---|---|
| `CEREBRAS_API_KEY` | Enables real Gemma 4 on Cerebras. Unset = simulated agent. |
| `CEREBRAS_MODEL` | Defaults to `gemma-4-31b`. |
| `BASELINE_BASE_URL` / `BASELINE_MODEL` / `BASELINE_API_KEY` | Optional real GPU endpoint for the speed comparison. Unset = simulated baseline at `BASELINE_SIM_TPS`. |
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
  pipeline/    adapter + mock_backend + airflow_backend + seed + gen_snapshot
  api/         routes_incident (webhook/start/SSE) + routes_actions (approval) + routes_speed
  audit/       append-only audit log
frontend/src/  IncidentConsole, AgentTimeline, RootCauseCard, RemediationPanel, SpeedCompare, ScreenshotDrop
docker/        multi-stage Dockerfile
scripts/       deploy_cloudrun.sh
```

## Notes & honesty

- With no `CEREBRAS_API_KEY`, the agent is a deterministic **simulation** so the UX is fully
  demoable offline; the orchestration code path is identical to the real one.
- The GPU baseline in the speed tab is always labeled **representative**; with real
  `BASELINE_*` settings it streams from an actual endpoint for a true side-by-side.
