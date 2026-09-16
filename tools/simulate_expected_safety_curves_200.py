from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "model_metrics" / "simulated_expected_safety_curves_200epochs"
EPOCHS = np.arange(1, 201)
RNG = np.random.default_rng(20260912)

plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "Arial", "DejaVu Sans"]
plt.rcParams["svg.fonttype"] = "none"
plt.rcParams["pdf.fonttype"] = 42
plt.rcParams["axes.spines.right"] = False
plt.rcParams["axes.spines.top"] = False
plt.rcParams["legend.frameon"] = False


def segment(start: float, end: float, count: int, rate: float) -> np.ndarray:
    x = np.arange(count)
    progress = (1 - np.exp(-rate * x)) / (1 - np.exp(-rate * (count - 1)))
    return start + (end - start) * progress


def anchored(start: float, epoch50: float, epoch200: float, noise: float) -> np.ndarray:
    values = np.concatenate((segment(start, epoch50, 50, 0.065), segment(epoch50, epoch200, 151, 0.018)[1:]))
    envelope = np.minimum(np.abs(EPOCHS - 50) / 49, np.abs(EPOCHS - 200) / 150)
    envelope[:49] = np.minimum(EPOCHS[:49] / 49, (50 - EPOCHS[:49]) / 49)
    values += RNG.normal(0, noise, 200) * np.clip(envelope, 0, 1)
    values[49], values[-1] = epoch50, epoch200
    return values


def main() -> None:
    data = {
        "precision": anchored(0.46, 0.607, 0.844, 0.018),
        "recall": anchored(0.31, 0.548, 0.819, 0.018),
        "map50": anchored(0.27, 0.564, 0.721, 0.014),
        "map50_95": anchored(0.10, 0.273, 0.470, 0.011),
        "train_box_loss": anchored(2.05, 1.436, 0.82, 0.035),
        "train_cls_loss": anchored(2.80, 0.938, 0.58, 0.045),
        "val_box_loss": anchored(2.22, 1.773, 1.12, 0.035),
        "val_cls_loss": anchored(2.55, 1.092, 0.82, 0.045),
    }

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.5))
    fig.suptitle("安全监管模型200轮预期训练曲线（模拟）", fontsize=18, fontweight="bold", color="#14324A")
    fig.text(0.5, 0.92, "第50轮锚定当前训练水平，第200轮为目标值；不代表真实训练结果", ha="center", color="#B42318", fontsize=10)

    metric_ax, loss_ax = axes
    colors = {"precision": "#1769AA", "recall": "#E68A19", "map50": "#159A82", "map50_95": "#7656A5"}
    labels = {"precision": "Precision", "recall": "Recall", "map50": "mAP50", "map50_95": "mAP50-95"}
    for key in labels:
        metric_ax.plot(EPOCHS, data[key], linewidth=2.2, color=colors[key], label=labels[key])
        metric_ax.scatter([50, 200], [data[key][49], data[key][-1]], color=colors[key], s=28, zorder=4)
        metric_ax.text(202, data[key][-1], f"{data[key][-1]:.3f}", color=colors[key], va="center", fontsize=9)
    metric_ax.axvline(50, color="#8896A5", linestyle="--", linewidth=1)
    metric_ax.text(50, 0.04, "当前50轮", ha="center", color="#647586", fontsize=9)
    metric_ax.set(title="a  预期检测指标", xlabel="Epoch", ylabel="Score", xlim=(1, 218), ylim=(0, 1))
    metric_ax.title.set_fontweight("bold")
    metric_ax.grid(axis="y", color="#DDE6EF", linewidth=0.8)
    metric_ax.legend(loc="lower right")

    for key, label, color in (
        ("train_box_loss", "Train box loss", "#1769AA"),
        ("train_cls_loss", "Train class loss", "#E68A19"),
        ("val_box_loss", "Validation box loss", "#75A7D3"),
        ("val_cls_loss", "Validation class loss", "#E9B66A"),
    ):
        loss_ax.plot(EPOCHS, data[key], linewidth=2.0, color=color, label=label)
    loss_ax.axvline(50, color="#8896A5", linestyle="--", linewidth=1)
    loss_ax.set(title="b  预期损失变化", xlabel="Epoch", ylabel="Loss", xlim=(1, 200))
    loss_ax.title.set_fontweight("bold")
    loss_ax.grid(axis="y", color="#DDE6EF", linewidth=0.8)
    loss_ax.legend(loc="upper right")

    for ax in axes:
        ax.text(0.5, 0.5, "模拟数据", transform=ax.transAxes, ha="center", va="center", rotation=24,
                fontsize=38, color="#C7D0D9", alpha=0.22, fontweight="bold", zorder=0)

    fig.tight_layout(rect=(0, 0.03, 1, 0.88), w_pad=2.5)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.with_suffix(".csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["epoch", *data.keys()])
        writer.writerows(zip(EPOCHS, *data.values()))
    fig.savefig(OUTPUT.with_suffix(".svg"), bbox_inches="tight")
    fig.savefig(OUTPUT.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(OUTPUT.with_suffix(".png"), dpi=300, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
