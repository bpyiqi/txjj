from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

from build_video_training_dataset import CLASSES, DATASET, ROOT, build


MODEL_DIR = ROOT / "backend" / "models"


def train(epochs: int, batch: int, imgsz: int, device: str | None, workers: int, include_auto_worker: bool) -> dict:
    dataset = build(include_auto_worker=include_auto_worker)
    if dataset["images"] < 20:
        raise ValueError(f"Too few labeled images for a first model: {dataset['images']}")
    from ultralytics import YOLO

    published = MODEL_DIR / (
        "construction_yolo_assisted.pt" if include_auto_worker else "construction_yolo_combined.pt"
    )
    summary_path = MODEL_DIR / (
        "assisted_training_summary.json" if include_auto_worker else "combined_training_summary.json"
    )

    base = ROOT / "yolo26n.pt"
    if not base.exists():
        raise FileNotFoundError(base)
    model = YOLO(str(base))
    result = model.train(
        data=str(DATASET / "dataset.yaml"),
        epochs=epochs,
        batch=batch,
        imgsz=imgsz,
        device=device,
        workers=workers,
        project=str(MODEL_DIR / "training_runs"),
        name="construction_assisted" if include_auto_worker else "construction_combined",
        exist_ok=True,
        pretrained=True,
        patience=12,
        seed=42,
        deterministic=True,
        plots=True,
    )
    best = Path(result.save_dir) / "weights" / "best.pt"
    if not best.exists():
        raise FileNotFoundError(f"Training completed without weights: {best}")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best, published)
    metrics = model.val(
        data=str(DATASET / "dataset.yaml"),
        split="val",
        imgsz=imgsz,
        batch=batch,
        device=device,
        workers=0,
    )
    summary = {
        "trained_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "weights": published.relative_to(ROOT).as_posix(),
        "dataset": dataset,
        "classes": CLASSES,
        "epochs": epochs,
        "batch": batch,
        "imgsz": imgsz,
        "device": device or "auto",
        "include_auto_worker": include_auto_worker,
        "metrics": {
            "precision": float(metrics.box.mp),
            "recall": float(metrics.box.mr),
            "map50": float(metrics.box.map50),
            "map50_95": float(metrics.box.map),
        },
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train the combined construction video detector")
    parser.add_argument("--epochs", type=int, default=35)
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--imgsz", type=int, default=320)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--device", default=None)
    parser.add_argument("--include-auto-worker", action="store_true")
    args = parser.parse_args()
    print(json.dumps(train(args.epochs, args.batch, args.imgsz, args.device, args.workers, args.include_auto_worker), ensure_ascii=False, indent=2))
