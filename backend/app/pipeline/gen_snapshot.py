"""Generate a Grafana/Airflow-style DAG + build-status snapshot PNG per scenario.

This is the image the alert 'carries' and that Gemma 4 vision reads. The DAG row
shows each stage with its status color; the bottom panel plots the scenario's
key failing metric (memory pegged at a limit, rows rejected, error rate, 429s).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

_STATE_COLOR = {"ok": "#2ea043", "fail": "#f85149", "skip": "#6e7681"}


def generate_snapshot(out_path: str, spec: Optional[dict[str, Any]] = None) -> str:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    if spec is None:
        from app.pipeline.scenarios import DEFAULT_SCENARIO_ID, get_scenario

        spec = get_scenario(DEFAULT_SCENARIO_ID).snapshot

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    fig = plt.figure(figsize=(10, 5.2), dpi=130)
    fig.patch.set_facecolor("#0f1419")

    # --- top: DAG ---
    ax = fig.add_axes([0.04, 0.55, 0.92, 0.4])
    ax.set_facecolor("#0f1419")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 3)
    ax.axis("off")
    ax.text(0.1, 2.7, spec["title"], color="#e6edf3", fontsize=13, fontweight="bold")
    ax.text(0.1, 2.35, spec["subtitle"], color="#f85149", fontsize=10)

    stages = spec["stages"]
    xs = [1.6, 4.6, 7.6][: len(stages)]
    for (name, status, state), x in zip(stages, xs):
        color = _STATE_COLOR.get(state, "#6e7681")
        box = FancyBboxPatch((x, 0.7), 1.9, 0.9, boxstyle="round,pad=0.02,rounding_size=0.1",
                             linewidth=2, edgecolor=color, facecolor="#161b22")
        ax.add_patch(box)
        ax.text(x + 0.95, 1.32, name, ha="center", color="#e6edf3", fontsize=12, fontweight="bold")
        ax.text(x + 0.95, 0.95, status, ha="center", color=color, fontsize=8.5)
    for x0 in (3.5, 6.5)[: max(0, len(stages) - 1)]:
        ax.annotate("", xy=(x0 + 1.1, 1.15), xytext=(x0, 1.15),
                    arrowprops=dict(arrowstyle="->", color="#6e7681", lw=1.6))

    # --- bottom: metric panel ---
    ax2 = fig.add_axes([0.08, 0.10, 0.86, 0.34])
    ax2.set_facecolor("#0d1117")
    limit = float(spec["limit"]) or 1.0
    xs2 = list(range(12))
    base = limit * 0.35
    peg = spec.get("peg", True)
    ys = []
    for i in xs2:
        v = base + (limit * 0.99 - base) * (i / 11)
        if peg:
            v = min(v, limit)
        ys.append(v)
    ax2.plot(xs2, ys, color="#f0883e", lw=2.2, marker="o", markersize=3)
    ax2.axhline(limit, color="#f85149", ls="--", lw=1.5)
    ax2.text(0.2, limit * 0.92, spec["limit_label"], color="#f85149", fontsize=9)
    ax2.set_title(spec["panel_title"], color="#e6edf3", fontsize=10, loc="left")
    ax2.set_ylim(0, limit * 1.15)
    ax2.tick_params(colors="#6e7681", labelsize=7)
    for spine in ax2.spines.values():
        spine.set_color("#30363d")

    fig.savefig(out_path, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_path


def generate_all() -> list[str]:
    """Render snapshots for every scenario (used at build/startup)."""
    from app.pipeline.scenarios import SCENARIOS

    return [generate_snapshot(s.snapshot_path, s.snapshot) for s in SCENARIOS.values()]


if __name__ == "__main__":
    print("\n".join(generate_all()))
