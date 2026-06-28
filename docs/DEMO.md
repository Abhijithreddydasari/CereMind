# CereMind - Demo Kit

Everything you need to record the 60-second video and submit to the hackathon.

---

## 60-second demo script (shot-by-shot)

Pre-roll setup (do before recording): run with a real `CEREBRAS_API_KEY` if possible (for
genuine speed numbers), have the app open at the **War Room** tab, and clear any prior incident
(reload the page). Optionally set `BASELINE_BASE_URL` to a real GPU endpoint for an honest race.

| Time | On screen | Say (voiceover) |
|---|---|---|
| 0:00-0:06 | Title card -> War Room, the red `transform` DAG snapshot visible | "A nightly ETL just failed. Normally on-call spends 20+ minutes digging. Watch CereMind." |
| 0:06-0:10 | Click **Simulate job-failed alert**. Timeline starts streaming | "The alert fires and CereMind auto-investigates - no human needed." |
| 0:10-0:18 | VISION event + specialists firing tools live | "Gemma 4 vision reads the dashboard, then three specialist agents pull logs, config history, and runbooks in parallel - on Cerebras, in seconds." |
| 0:18-0:28 | ROOT CAUSE card with evidence chips + the timer "~X s" | "Root cause, with every claim cited: a config change cut transform memory 8GB to 2GB, so it was OOMKilled. The whole multi-hop investigation took seconds." |
| 0:28-0:36 | Approval gate; click **Approve & apply fix** | "Read-only by default. The fix is high-risk, so it waits for one click - then CereMind reverts the change and reruns the job." |
| 0:36-0:42 | EXEC + VERIFY -> "Resolved - pipeline green" | "Reran to green, with a full audit trail. Incident closed." |
| 0:42-0:56 | Switch to **Cerebras vs GPU**, click run; both panes stream | "Same root-cause prompt, two engines. Cerebras finishes while the GPU baseline is still typing - that speed is what makes an interactive war-room copilot possible." |
| 0:56-1:00 | Logo + tagline | "CereMind. Gemma 4 on Cerebras. It doesn't just find the problem - it fixes it." |

Recording tips: 1280x720+, hide notifications/tabs/keys, keep cursor movements deliberate.
The deterministic mock means every take is identical.

---

## Discord submission - project description

**CereMind - the agentic incident-response copilot that fixes, not just finds.**

Most "AI for incidents" tools summarize or retrieve. CereMind is an autonomous on-call engineer:
when a pipeline job fails, it auto-triggers, uses **Gemma 4 vision** to read the alert's
dashboard, then runs a **multi-agent** investigation (an Incident Commander coordinating
telemetry, change, and knowledge specialists) that **calls real tools** - logs, metrics, config
diffs, runbook + past-incident search (EmbeddingGemma + Qdrant, permission-aware). It produces a
**cited root cause**, then - behind a risk-tiered **human approval gate** - applies the fix
(revert the offending config) and **reruns the job to green**, with a full audit log.

The differentiator is **speed as a capability**: on Cerebras, Gemma 4 31B runs the entire
multi-hop loop in ~10-15 seconds instead of the minutes other AI-SRE tools take, turning
incident response from a submit-and-wait batch job into a real-time, interactive war room. We
include a live side-by-side that races the same prompt on Cerebras vs a GPU baseline.

Enterprise-ready by design: stateless on Cloud Run, secrets in Secret Manager, permission-aware
retrieval, read-only-by-default with gated writes, append-only audit log, and a swappable
pipeline adapter (mock -> Apache Airflow / CI). Because Gemma 4 and EmbeddingGemma are
open-weight, the whole stack can run sovereign/self-hosted with zero data egress.

Tracks: Enterprise Impact (primary), Multiverse Agents (multi-agent + multimodal).
Stack: Gemma 4 31B on Cerebras, EmbeddingGemma, FastAPI, React, Qdrant, Google Cloud Run.

[Live demo: <CLOUD_RUN_URL>] [Video: <LINK>] [Code: <REPO>]

---

## X / Twitter post

> We built CereMind: an AI on-call engineer that doesn't just find incidents - it fixes them.
>
> A pipeline fails -> @googlegemma Gemma 4 vision reads the dashboard -> multi-agent investigation
> calls real tools -> cited root cause -> one-click approve -> auto-revert + rerun to green.
>
> The kicker: on @Cerebras it runs the whole multi-hop investigation in seconds, not minutes.
> That speed is what turns incident response into a real-time war-room copilot.
>
> Gemma 4 + EmbeddingGemma + Cerebras, deployable on Google Cloud. #Gemma4 #Cerebras
>
> [60s demo video + side-by-side speed test below]

Reminder: post the video natively on X and tag **@Cerebras** and **@googlegemma** (Track 2 is
organic impressions - encourage genuine reshares; no paid promotion).
