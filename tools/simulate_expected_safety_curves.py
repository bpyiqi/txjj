from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "model_metrics" / "simulated_expected_safety_curves"
EPOCHS = np.arange(1, 51)
RNG = np.random.default_rng(20260912)

plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "Arial", "DejaVu Sans"]
plt.rcParams["svg.fonttype"] = "none"
plt.rcParams["pdf.fonttype"] = 42
plt.rcParams["axes.spines.right"] = False
plt.rcParams["axes.spines.top"] = False
plt.rcParams["legend.frameon"] = False


def rising(start: float, target: float, rate: float, noise: float) -> np.ndarray:
    progress = (1 - np.exp(-rate * (EPOCHS - 1))) / (1 - np.exp(-rate * 49))
    values = start + (target - start) * progress
    values += RNG.normal(0, noise, len(EPOCHS)) * (1 - progress) ** 0.7
    values = np.clip(values, 0, 1)
    values[-1] = target
    return values


def falling(start: float, target: float, rate: float, noise: float) -> np.ndarray:
    progress = (1 - np.exp(-rate * (EPOCHS - 1))) / (1 - np.exp(-rate * 49))
    values = start + (target - start) * progress
    values += RNG.normal(0, noise, len(EPOCHS)) * (1 - progress) ** 0.7
    values[-1] = target
    return values


def main() -> None:
    data = {
        "precision": rising(0.48, 0.844, 0.085, 0.035),
        "recall": rising(0.39, 0.819, 0.072, 0.032),
        "map50": rising(0.24, 0.721, 0.070, 0.025),
        "map50_95": rising(0.10, 0.470, 0.060, 0.018),
        "train_box_loss": falling(2.05, 0.82, 0.055, 0.055),
        "train_cls_loss": falling(2.80, 0.62, 0.070, 0.070),
        "val_box_loss": falling(2.22, 1.08, 0.050, 0.065),
        "val_cls_loss": falling(2.55, 0.88, 0.060, 0.075),
    }

    fig, axes = plt.subplots(1, 2, figsize=(12, 5.4))
    fig.suptitle("安全监管模型预期训练曲线（模拟）", fontsize=18, fontweight="bold", color="#14324A")
    fig.text(0.5, 0.92, "用于观察目标指标对应的合理趋势，不代表真实训练结果", ha="center", color="#B42318", fontsize=10)

    metric_ax, loss_ax = axes
    colors = {"precision": "#1769AA", "recall": "#E68A19", "map50": "#159A82", "map50_95": "#7656A5"}
    labels = {"precision": "Precision", "recall": "Recall", "map50": "mAP50", "map50_95": "mAP50-95"}
    for key in ("precision", "recall", "map50", "map50_95"):
        metric_ax.plot(EPOCHS, data[key], linewidth=2.4, color=colors[key], label=labels[key])
        metric_ax.scatter([50], [data[key][-1]], color=colors[key], s=35, zorder=4)
        metric_ax.text(50.5, data[key][-1], f"{data[key][-1]:.3f}", color=colors[key], va="center", fontsize=9)
    metric_ax.set_title("a  预期检测指标", loc="left", fontsize=13, fontweight="bold")
    metric_ax.set_xlabel("Epoch")
    metric_ax.set_ylabel("Score")
    metric_ax.set_xlim(1, 55)
    metric_ax.set_ylim(0, 1)
    metric_ax.grid(axis="y", color="#DDE6EF", linewidth=0.8)
    metric_ax.legend(loc="lower right")

    for key, label, color in (
        ("train_box_loss", "Train box loss", "#1769AA"),
        ("train_cls_loss", "Train class loss", "#E68A19"),
        ("val_box_loss", "Validation box loss", "#75A7D3"),
        ("val_cls_loss", "Validation class loss", "#E9B66A"),
    ):
        loss_ax.plot(EPOCHS, data[key], linewidth=2.2, color=color, label=label)
    loss_ax.set_title("b  预期损失变化", loc="left", fontsize=13, fontweight="bold")
    loss_ax.set_xlabel("Epoch")
    loss_ax.set_ylabel("Loss")
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
    print(OUTPUT.with_suffix(".png"))


if __name__ == "__main__":
    main()
