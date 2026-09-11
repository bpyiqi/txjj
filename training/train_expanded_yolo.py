from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

from prepare_expanded_dataset import CLASSES, DATASET, ROOT, prepare_dataset
from validate_expanded_labels import validate


MODEL_DIR = ROOT / "backend" / "models"
RUN_DIR = MODEL_DIR / "training_runs" / "expanded_construction"
PUBLISHED = MODEL_DIR / "construction_yolo_expanded.pt"


def train(epochs: int, batch: int, imgsz: int, device: str | None, workers: int = 0) -> dict:
    dataset = prepare_dataset()
    validation = validate()
    if validation["errors"]:
        raise ValueError("标签检查失败：" + "；".join(validation["errors"][:5]))
    if validation["annotated_images"] < 30 or validation["box_count"] < 50:
        raise ValueError(f"标注量不足：当前 {validation['annotated_images']} 张图片、{validation['box_count']} 个框；至少先标注30张图片和50个框")
    from ultralytics import YOLO

    base = ROOT / "yolo26n.pt"
    if not base.exists():
        raise FileNotFoundError(f"找不到基础模型：{base}")
    model = YOLO(str(base))
    result = model.train(
        data=str(DATASET / "dataset.yaml"),
        epochs=epochs,
        batch=batch,
        imgsz=imgsz,
        device=device,
        workers=workers,
        project=str(MODEL_DIR / "training_runs"),
        name="expanded_construction",
        exist_ok=True,
        pretrained=True,
        patience=15,
        plots=True,
    )
    best = Path(result.save_dir) / "weights" / "best.pt"
    if not best.exists():
        raise FileNotFoundError(f"训练完成但未找到权重：{best}")
    shutil.copy2(best, PUBLISHED)
    metrics = model.val(data=str(DATASET / "dataset.yaml"), split="test", imgsz=imgsz, batch=batch, device=device, workers=0)
    summary = {
        "trained_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "weights": str(PUBLISHED.relative_to(ROOT)),
        "dataset": dataset,
        "classes": CLASSES,
        "labels": validation,
        "epochs": epochs,
        "batch": batch,
        "imgsz": imgsz,
        "device": device or "auto",
        "metrics": {
            "precision": float(metrics.box.mp),
            "recall": float(metrics.box.mr),
            "map50": float(metrics.box.map50),
            "map50_95": float(metrics.box.map),
        },
    }
    (MODEL_DIR / "expanded_training_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="训练扩展版通信施工目标检测模型")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--device", default=None)
    args = parser.parse_args()
    print(json.dumps(train(args.epochs, args.batch, args.imgsz, args.device, args.workers), ensure_ascii=False, indent=2))
