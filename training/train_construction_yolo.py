from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

from build_construction_dataset import DATASET, ROOT, build_dataset


MODEL_DIR = ROOT / "backend" / "models"


def _publish(best: Path, epochs: int, device: str | None, dataset: dict, metrics_source, image_size: int) -> dict:
    target = MODEL_DIR / "construction_yolo.pt"
    shutil.copy2(best, target)
    metrics = {key: float(value) for key, value in metrics_source.results_dict.items()}
    manifest_hash = hashlib.sha256((DATASET / "manifest.json").read_bytes()).hexdigest()
    summary = {
        "trained_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "base_model": "yolo26n.pt",
        "weights": target.relative_to(ROOT).as_posix(),
        "weight_selection": "last_epoch_for_demo_calibration",
        "epochs": epochs,
        "image_size": image_size,
        "device": device or "auto",
        "dataset": dataset,
        "dataset_manifest_sha256": manifest_hash,
        "metrics": metrics,
        "scope": "竞赛演示小样本模型，部署前需扩充独立现场数据并重新验证",
    }
    (MODEL_DIR / "training_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def train(epochs: int, device: str | None, publish_existing: bool = False, image_size: int = 320) -> dict:
    from ultralytics import YOLO

    dataset = build_dataset()
    existing = MODEL_DIR / "training_runs" / "construction_objects" / "weights" / "last.pt"
    if publish_existing:
        if not existing.exists():
            raise FileNotFoundError("没有可发布的已训练权重")
        model = YOLO(str(existing))
        metrics = model.val(data=str(DATASET / "dataset.yaml"), device=device, workers=0, imgsz=image_size)
        return _publish(existing, epochs, device, dataset, metrics, image_size)

    model = YOLO("yolo26n.pt")
    result = model.train(
        data=str(DATASET / "dataset.yaml"),
        epochs=epochs,
        imgsz=image_size,
        batch=8,
        workers=0,
        device=device,
        project=str(MODEL_DIR / "training_runs"),
        name="construction_objects",
        exist_ok=True,
        seed=42,
        deterministic=True,
        plots=True,
        freeze=10,
    )
    final_weights = Path(result.save_dir) / "weights" / "last.pt"
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    metrics = YOLO(str(final_weights)).val(data=str(DATASET / "dataset.yaml"), device=device, workers=0, imgsz=image_size)
    return _publish(final_weights, epochs, device, dataset, metrics, image_size)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="训练通信施工三目标YOLO检测模型")
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--device", default=None, help="例如 0 或 cpu；默认自动选择")
    parser.add_argument("--imgsz", type=int, default=320)
    parser.add_argument("--publish-existing", action="store_true", help="验证并发布已有best.pt，不重新训练")
    args = parser.parse_args()
    print(json.dumps(train(args.epochs, args.device, args.publish_existing, args.imgsz), ensure_ascii=False, indent=2))
