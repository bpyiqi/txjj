from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend" / "models" / "training_runs" / "safety_ppe_yolov8n" / "results.csv"
OUTPUT = ROOT / "output" / "model_metrics" / "safety_training_curves"


plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "Arial", "DejaVu Sans"]
plt.rcParams["svg.fonttype"] = "none"
plt.rcParams["pdf.fonttype"] = 42
plt.rcParams["axes.spines.right"] = False
plt.rcParams["axes.spines.top"] = False
plt.rcParams["axes.linewidth"] = 0.9
plt.rcParams["font.size"] = 10


def load_results() -> dict[str, list[float]]:
    with SOURCE.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise RuntimeError(f"训练结果为空：{SOURCE}")
    return {
        key.strip(): [float(row[key]) for row in rows]
        for key in rows[0]
    }


def smooth(values: list[float], window: int = 5) -> list[float]:
    return [sum(values[max(0, i - window + 1) : i + 1]) / min(i + 1, window) for i in range(len(values))]


def draw_series(ax, epochs, data, keys, labels, colors, ylabel):
    for key, label, color in zip(keys, labels, colors):
        values = data[key]
        ax.plot(epochs, values, color=color, alpha=0.18, linewidth=1)
        ax.plot(epochs, smooth(values), color=color, linewidth=2.2, label=label)
    ax.set_xlabel("Epoch")
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", color="#DDE6EF", linewidth=0.7)
    ax.legend(loc="best", fontsize=8)


def main() -> None:
    data = load_results()
    epochs = data["epoch"]
    blue, teal, orange = "#1769AA", "#159A82", "#E68A19"
    fig, axes = plt.subplots(2, 2, figsize=(11.8, 7.2))
    fig.suptitle("YOLOv8n 安全监管模型训练曲线", fontsize=17, fontweight="bold", color="#14324A")

    draw_series(
        axes[0, 0], epochs, data,
        ["train/box_loss", "train/cls_loss", "train/dfl_loss"],
        ["Box loss", "Class loss", "DFL loss"],
        [blue, orange, teal], "Training loss",
    )
    axes[0, 0].set_title("a  训练损失", loc="left", fontweight="bold")

    draw_series(
        axes[0, 1], epochs, data,
        ["val/box_loss", "val/cls_loss", "val/dfl_loss"],
        ["Box loss", "Class loss", "DFL loss"],
        [blue, orange, teal], "Validation loss",
    )
    axes[0, 1].set_title("b  验证损失", loc="left", fontweight="bold")

    draw_series(
        axes[1, 0], epochs, data,
        ["metrics/precision(B)", "metrics/recall(B)"],
        ["Precision", "Recall"], [blue, orange], "Score",
    )
    axes[1, 0].set_ylim(0, 1)
    axes[1, 0].set_title("c  检测精确率与召回率", loc="left", fontweight="bold")

    draw_series(
        axes[1, 1], epochs, data,
        ["metrics/mAP50(B)", "metrics/mAP50-95(B)"],
        ["mAP50", "mAP50-95"], [teal, blue], "mAP",
    )
    axes[1, 1].set_ylim(0, 1)
    axes[1, 1].set_title("d  平均精度", loc="left", fontweight="bold")

    best_index = max(range(len(epochs)), key=lambda i: data["metrics/mAP50-95(B)"][i])
    best_epoch = int(epochs[best_index])
    best_value = data["metrics/mAP50-95(B)"][best_index]
    axes[1, 1].scatter([best_epoch], [best_value], s=38, color="#C83E3A", zorder=5)
    axes[1, 1].annotate(
        f"Best epoch {best_epoch}\nmAP50-95 = {best_value:.3f}",
        (best_epoch, best_value), xytext=(-82, 28), textcoords="offset points",
        arrowprops={"arrowstyle": "->", "color": "#C83E3A"}, fontsize=8,
    )

    final = {key: data[key][-1] for key in [
        "metrics/precision(B)", "metrics/recall(B)", "metrics/mAP50(B)", "metrics/mAP50-95(B)"
    ]}
    fig.text(
        0.5, 0.018,
        "第50轮：Precision {:.3f}   Recall {:.3f}   mAP50 {:.3f}   mAP50-95 {:.3f}   |   淡线为逐轮值，实线为5轮移动平均".format(*final.values()),
        ha="center", color="#52687A", fontsize=9,
    )

    fig.tight_layout(rect=(0, 0.055, 1, 0.95), h_pad=1.4, w_pad=1.5)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT.with_suffix(".svg"), bbox_inches="tight")
    fig.savefig(OUTPUT.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(OUTPUT.with_suffix(".png"), dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(OUTPUT.with_suffix(".png"))


if __name__ == "__main__":
    main()
