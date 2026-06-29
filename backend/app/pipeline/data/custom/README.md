# Custom incident dashboards (drop-in override)

Drop a dashboard image here named exactly after the scenario id and CereMind will
serve **your** image to Gemma 4 vision instead of the auto-generated one. No code
change or rebuild needed.

| Scenario id        | Drop file as           | Incident                                   |
| ------------------ | ---------------------- | ------------------------------------------ |
| `oom_memory_cut`   | `oom_memory_cut.png`   | transform OOMKilled after a memory cut     |
| `schema_drift`     | `schema_drift.png`     | transform data-contract violation          |
| `dependency_bump`  | `dependency_bump.png`  | transform ArrowInvalid after a pyarrow bump|
| `vendor_ratelimit` | `vendor_ratelimit.png` | ingest HTTP 429 after a concurrency bump   |

Accepted extensions: `.png`, `.jpg`, `.jpeg`, `.webp` (png recommended).
Recommended size: ~1024x720 or larger, dark background.

Precedence: `data/custom/<id>.png` (yours) > `data/snapshot_<id>.png` (auto-generated).
Auto-generation never overwrites files in this folder.

---

## ChatGPT / image-model prompts (one per scenario)

Paste these into an image model (e.g. ChatGPT image gen) to get a realistic
"observability dashboard screenshot". Keep the dark theme so the bounding-box
overlay in the UI reads well.

**Shared style suffix** (append to any prompt below):
> Dark navy observability dashboard UI, Grafana/Datadog aesthetic, cyan accent
> lines, crisp small sans-serif labels, subtle grid, panels with rounded corners,
> 16:10 screenshot, no people, no logos, high detail, flat UI.

1. **oom_memory_cut**
> A monitoring dashboard for an Airflow job `acmeshop_nightly_etl` run_2004 marked
> FAILED. Top shows a 3-stage DAG: `ingest` green, `transform` red (OOMKilled),
> `load` grey (skipped). Main panel: a memory-usage line chart in MB climbing
> steadily into a red dashed `worker_memory_limit = 2048MB` line. Stat tiles: Peak
> mem 2048MB, Healthy peak 6912MB, Failed in 37s. A log panel with a red line
> "OOMKilled: memory limit 2048MB exceeded".

2. **schema_drift**
> A monitoring dashboard for `acmeshop_orders_sync` run_5567 FAILED. DAG: ingest
> green, transform red (contract violation), load skipped. Main panel: a
> "rows rejected by data contract" chart that is flat near zero then steps up to
> 100% (412,889 rows). Stat tiles: Rows rejected 100%, Contract orders@v3, Failed
> in 19s. Log panel red line: "not-null column 'customer_id' missing (source emits
> 'cust_id')".

3. **dependency_bump**
> A monitoring dashboard for `acmeshop_reco_features` run_8123 FAILED. DAG: ingest
> green, transform red (ArrowInvalid), load skipped. Main panel: a task error-rate
> chart that is 0% then jumps to 100% at a fixed point. Stat tiles: Error rate
> 100%, pyarrow 14 -> 17, Failed in 12s. Log panel red line:
> "pyarrow.lib.ArrowInvalid: 'use_legacy_dataset' removed in pyarrow 16".

4. **vendor_ratelimit**
> A monitoring dashboard for `acmeshop_partner_ingest` run_3310 FAILED. DAG:
> ingest red (HTTP 429), transform grey, load grey. Main panel: "vendor HTTP 429
> responses/min" that is quiet then spikes sharply up to ~240. Stat tiles: Peak
> 429/min 240, Concurrency 4 -> 32, Failed in 54s. Log panel red line:
> "HTTP 429 Too Many Requests x214 - 32 concurrent > 8 contracted".
