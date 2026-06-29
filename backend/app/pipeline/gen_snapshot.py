"""Render a realistic Grafana/Airflow-style incident dashboard PNG per scenario.

This is the image the alert "carries" and that Gemma 4 vision reads. Each
scenario produces a visually distinct dashboard so the demo never shows the same
screenshot twice:

  * a header bar with the job title, failure subtitle and a SEV badge
  * the DAG row (ingest -> transform -> load) colored by per-stage status
  * a large time-series panel for the scenario's key failing metric, with a
    gradient fill, the breached threshold and a "breach" annotation. The series
    shape varies by metric (memory ramp, contract step, error-rate step, 429
    spike), so each picture reads differently.
  * three stat tiles summarizing the blast radius
  * a terminal-style log tail with the decisive error line highlighted in red

If the user drops a hand-made / ChatGPT-generated dashboard at
``data/custom/<scenario_id>.png`` it overrides this renderer (see
``Scenario.snapshot_path``); ``generate_all`` never overwrites those.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

# Dark, slightly blue Grafana palette tuned to match the CereMind UI.
_BG = "#0a1422"
_PANEL = "#0f1c2e"
_PANEL_EDGE = "#22344a"
_TEXT = "#d4e4fa"
_MUTED = "#7f93ad"
_GRID = "#1b2c41"
_ACCENT = "#22d3ee"
_OK = "#34d399"
_FAIL = "#ff6b6b"
_WARN = "#f4b740"
_SKIP = "#5b6b80"

_STATE_COLOR = {"ok": _OK, "fail": _FAIL, "skip": _SKIP}


def _series(limit: float, shape: str, n: int = 26) -> list[float]:
    """Deterministic metric series whose silhouette differs per failure class."""
    lo = limit * 0.32
    ys: list[float] = []
    for i in range(n):
        f = i / (n - 1)
        if shape == "step":  # healthy, then a hard jump to the ceiling (errors/rejects)
            v = limit * 0.02 if f < 0.55 else limit
        elif shape == "spike":  # quiet, then a steep climbing spike (429 storm)
            v = limit * 0.04 if f < 0.45 else limit * (0.04 + (f - 0.45) / 0.55) ** 0.6 * 1.0
            v = min(v, limit)
        else:  # "ramp": steady climb into the cap (memory)
            v = lo + (limit * 0.99 - lo) * f
        ys.append(min(v, limit))
    return ys


def _shape_for(unit: str) -> str:
    u = (unit or "").lower()
    if "%" in u or "row" in u:
        return "step"
    if "429" in u or "/min" in u or "min" in u:
        return "spike"
    return "ramp"


def generate_snapshot(out_path: str, spec: Optional[dict[str, Any]] = None) -> str:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    if spec is None:
        from app.pipeline.scenarios import DEFAULT_SCENARIO_ID, get_scenario

        spec = get_scenario(DEFAULT_SCENARIO_ID).snapshot

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    fig = plt.figure(figsize=(11.6, 7.2), dpi=140)
    fig.patch.set_facecolor(_BG)

    # Full-figure overlay axes (0..1) for panels, badges and text.
    bg = fig.add_axes([0, 0, 1, 1])
    bg.set_xlim(0, 1)
    bg.set_ylim(0, 1)
    bg.axis("off")

    def panel(x, y, w, h, edge=_PANEL_EDGE, face=_PANEL):
        bg.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.004,rounding_size=0.012",
                                    linewidth=1.2, edgecolor=edge, facecolor=face, zorder=1))

    # ---------------------------------------------------------------- header --
    bg.text(0.035, 0.945, spec["title"], color=_TEXT, fontsize=17, fontweight="bold", zorder=3)
    bg.text(0.035, 0.905, spec["subtitle"], color=_FAIL, fontsize=11.5, fontweight="bold", zorder=3)
    # live + grafana-ish breadcrumb
    bg.add_patch(plt.Circle((0.037, 0.872), 0.006, color=_FAIL, zorder=3))
    bg.text(0.05, 0.866, "LIVE  -  Airflow / Grafana incident view  -  last 5m",
            color=_MUTED, fontsize=9, zorder=3)
    # SEV badge
    sev = spec.get("sev", "SEV-2")
    panel(0.86, 0.9, 0.105, 0.06, edge=_FAIL, face="#2a1414")
    bg.text(0.9125, 0.918, sev, color=_FAIL, fontsize=14, fontweight="bold",
            ha="center", zorder=3)

    # ------------------------------------------------------------------- DAG --
    panel(0.035, 0.7, 0.93, 0.135)
    bg.text(0.05, 0.805, "DAG", color=_MUTED, fontsize=9.5, fontweight="bold", zorder=3)
    stages = spec["stages"]
    n = len(stages)
    box_w, gap = 0.235, 0.055
    total = n * box_w + (n - 1) * gap
    start = (1 - total) / 2
    centers = []
    for i, (name, status, state) in enumerate(stages):
        x = start + i * (box_w + gap)
        color = _STATE_COLOR.get(state, _SKIP)
        face = "#241318" if state == "fail" else "#0c1828"
        bg.add_patch(FancyBboxPatch((x, 0.715), box_w, 0.066,
                                    boxstyle="round,pad=0.004,rounding_size=0.014",
                                    linewidth=2, edgecolor=color, facecolor=face, zorder=2))
        cx = x + box_w / 2
        centers.append(cx)
        bg.add_patch(plt.Circle((x + 0.022, 0.748), 0.006, color=color, zorder=3))
        bg.text(x + 0.04, 0.757, name, color=_TEXT, fontsize=12.5, fontweight="bold",
                va="center", zorder=3)
        bg.text(x + 0.04, 0.731, status, color=color, fontsize=8.8, va="center", zorder=3)
    for a, b in zip(centers, centers[1:]):
        bg.annotate("", xy=(b - box_w / 2 - 0.004, 0.748), xytext=(a + box_w / 2 + 0.004, 0.748),
                    arrowprops=dict(arrowstyle="-|>", color=_MUTED, lw=1.8), zorder=2)

    # --------------------------------------------------------- metric panel ---
    panel(0.035, 0.255, 0.66, 0.4)
    ax = fig.add_axes([0.085, 0.305, 0.55, 0.30])
    ax.set_facecolor(_PANEL)
    limit = float(spec["limit"]) or 1.0
    unit = spec.get("unit", "")
    shape = spec.get("shape") or _shape_for(unit)
    ys = _series(limit, shape)
    xs = list(range(len(ys)))
    ax.plot(xs, ys, color=_ACCENT, lw=2.4, zorder=3)
    ax.fill_between(xs, ys, color=_ACCENT, alpha=0.14, zorder=2)
    # threshold + breach annotation
    ax.axhline(limit, color=_FAIL, ls="--", lw=1.6, zorder=3)
    ax.text(0.3, limit * 1.02, spec.get("limit_label", ""), color=_FAIL, fontsize=9.5,
            fontweight="bold", va="bottom")
    breach = next((i for i, v in enumerate(ys) if v >= limit * 0.999), None)
    if breach is not None:
        ax.scatter([breach], [limit], s=70, color=_FAIL, zorder=5, edgecolor="white", linewidth=0.8)
        ax.annotate("breach", xy=(breach, limit), xytext=(breach - 6, limit * 0.74),
                    color=_FAIL, fontsize=9.5, fontweight="bold",
                    arrowprops=dict(arrowstyle="->", color=_FAIL, lw=1.4))
    ax.set_ylim(0, limit * 1.18)
    ax.set_xlim(0, len(ys) - 1)
    ax.set_title(spec.get("panel_title", "") + (f"   ({unit})" if unit else ""),
                 color=_TEXT, fontsize=10.5, loc="left", fontweight="bold", pad=8)
    ax.grid(True, color=_GRID, lw=0.8)
    ax.tick_params(colors=_MUTED, labelsize=7.5)
    ax.set_xticklabels([])
    for spine in ax.spines.values():
        spine.set_color(_PANEL_EDGE)

    # ----------------------------------------------------------- stat tiles ---
    stats = spec.get("stats") or []
    tile_x, tile_w, tile_h = 0.715, 0.25, 0.108
    bg.text(0.715, 0.625, "BLAST RADIUS", color=_MUTED, fontsize=9.5, fontweight="bold", zorder=3)
    for i, (label, value) in enumerate(stats[:3]):
        ty = 0.52 - i * (tile_h + 0.022)
        accent = _FAIL if i == 0 else (_WARN if i == 1 else _ACCENT)
        panel(tile_x, ty, tile_w, tile_h)
        bg.add_patch(plt.Rectangle((tile_x, ty), 0.006, tile_h, color=accent, zorder=3))
        bg.text(tile_x + 0.02, ty + tile_h - 0.03, value, color=_TEXT, fontsize=18,
                fontweight="bold", va="center", zorder=3)
        bg.text(tile_x + 0.02, ty + 0.022, label.upper(), color=_MUTED, fontsize=8.5,
                fontweight="bold", va="center", zorder=3)

    # ------------------------------------------------------------- log tail ---
    panel(0.035, 0.035, 0.93, 0.185, face="#070f1a")
    bg.text(0.05, 0.188, "log tail  -  " + stages[0][0] + " / transform", color=_MUTED,
            fontsize=9, fontweight="bold", zorder=3)
    error_line = spec.get("error_line", "")
    log_lines = [
        ("$ kubectl logs -f " + spec["title"].split(" ")[0], _MUTED),
        ("INFO  pipeline stage started ...", _MUTED),
        (error_line, _FAIL),
        ("ERROR task failed; downstream tasks skipped.", _FAIL),
    ]
    for i, (line, color) in enumerate(log_lines):
        bg.text(0.05, 0.158 - i * 0.032, line, color=color, fontsize=9.6,
                family="monospace", zorder=3)

    fig.savefig(out_path, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_path


def generate_all() -> list[str]:
    """Render snapshots for every scenario (used at build/startup).

    Always renders to the *generated* path so a user-dropped custom dashboard at
    ``data/custom/<id>.png`` is never overwritten.
    """
    from app.pipeline.scenarios import SCENARIOS

    return [generate_snapshot(s.generated_snapshot_path, s.snapshot) for s in SCENARIOS.values()]


if __name__ == "__main__":
    print("\n".join(generate_all()))
