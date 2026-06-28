"""Generate a Grafana/Airflow-style DAG + build-status snapshot PNG.

This is the image the alert 'carries' and that Gemma 4 vision reads: it shows
the ingest -> transform -> load DAG with `transform` red, plus a memory panel
pegged at the (lowered) limit.
"""
from __future__ import annotations

from pathlib import Path


def generate_snapshot(out_path: str) -> str:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    fig = plt.figure(figsize=(10, 5.2), dpi=130)
    fig.patch.set_facecolor("#0f1419")

    # --- top: DAG ---
    ax = fig.add_axes([0.04, 0.55, 0.92, 0.4])
    ax.set_facecolor("#0f1419")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 3)
    ax.axis("off")
    ax.text(0.1, 2.7, "acmeshop_nightly_etl  -  run_2004", color="#e6edf3",
            fontsize=13, fontweight="bold")
    ax.text(0.1, 2.35, "schedule  -  FAILED after 37s", color="#f85149", fontsize=10)

    stages = [("ingest", "#2ea043", 1.6), ("transform", "#f85149", 4.6), ("load", "#6e7681", 7.6)]
    statuses = ["success", "FAILED (OOMKilled)", "skipped"]
    for (name, color, x), status in zip(stages, statuses):
        box = FancyBboxPatch((x, 0.7), 1.9, 0.9, boxstyle="round,pad=0.02,rounding_size=0.1",
                             linewidth=2, edgecolor=color, facecolor="#161b22")
        ax.add_patch(box)
        ax.text(x + 0.95, 1.32, name, ha="center", color="#e6edf3", fontsize=12, fontweight="bold")
        ax.text(x + 0.95, 0.95, status, ha="center", color=color, fontsize=8.5)
    for x0 in (3.5, 6.5):
        ax.annotate("", xy=(x0 + 1.1, 1.15), xytext=(x0, 1.15),
                    arrowprops=dict(arrowstyle="->", color="#6e7681", lw=1.6))

    # --- bottom: memory panel ---
    ax2 = fig.add_axes([0.08, 0.10, 0.86, 0.34])
    ax2.set_facecolor("#0d1117")
    xs = list(range(12))
    limit = 2048
    base = limit * 0.35
    ys = [base + (limit * 0.99 - base) * (i / 11) for i in xs]
    ys = [min(y, limit) for y in ys]
    ax2.plot(xs, ys, color="#f0883e", lw=2.2, marker="o", markersize=3)
    ax2.axhline(limit, color="#f85149", ls="--", lw=1.5)
    ax2.text(0.2, limit * 0.92, "worker_memory_limit = 2048MB", color="#f85149", fontsize=9)
    ax2.set_title("transform: worker memory (MB)", color="#e6edf3", fontsize=10, loc="left")
    ax2.set_ylim(0, limit * 1.15)
    ax2.tick_params(colors="#6e7681", labelsize=7)
    for spine in ax2.spines.values():
        spine.set_color("#30363d")

    fig.savefig(out_path, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_path


if __name__ == "__main__":
    from app.pipeline.seed import SNAPSHOT_PATH

    print(generate_snapshot(SNAPSHOT_PATH))
