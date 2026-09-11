from __future__ import annotations

import argparse
import hashlib
import json
import os
import os
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "backend" / "models"
GENERATED_DIR = ROOT / "datasets" / "safety_ppe"
CLASSES = [
    "helmet", "gloves", "vest", "boots", "goggles", "none", "Person",
    "no_helmet", "no_goggle", "no_gloves", "no_boots",
]
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def configure_console() -> None:
    """Enable ANSI progress rendering in Windows cmd; use plain output when redirected."""
    if os.name != "nt":
        return
    import ctypes

    kernel32 = ctypes.windll.kernel32
    enabled = False
    for stream_id in (-11, -12):  # stdout, stderr
        handle = kernel32.GetStdHandle(stream_id)
        mode = ctypes.c_ulong()
        if handle and kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            enabled = bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004)) or enabled
    if not enabled:
        os.environ.setdefault("GITHUB_ACTIONS", "1")


def find_dataset(explicit: str | None = None) -> Path:
    candidates = ([Path(explicit)] if explicit else []) + [
        ROOT / "construction-ppe",
        ROOT.parent / "construction-ppe",
        ROOT.parents[1] / "construction-ppe",
    ]
    for candidate in candidates:
        if (candidate / "data.yaml").exists() and (candidate / "images" / "train").is_dir():
            return candidate.resolve()
    raise FileNotFoundError("未找到 construction-ppe 数据集；请放在项目同级目录，或使用 --data 指定路径")


def audit_dataset(dataset: Path) -> dict:
    split_stats = {}
    class_counts: Counter[int] = Counter()
    invalid_labels: list[str] = []
    for split in ("train", "val", "test"):
        image_dir = dataset / "images" / split
        label_dir = dataset / "labels" / split
        images = {path.stem: path for path in image_dir.iterdir() if path.suffix.lower() in IMAGE_EXTENSIONS}
        labels = {path.stem: path for path in label_dir.glob("*.txt")}
        box_count = 0
        for label_path in labels.values():
            for line_number, line in enumerate(label_path.read_text(encoding="utf-8").splitlines(), start=1):
                parts = line.split()
                try:
                    class_id = int(parts[0])
                    coords = [float(value) for value in parts[1:]]
                    valid = len(coords) == 4 and 0 <= class_id < len(CLASSES) and all(0 <= value <= 1 for value in coords)
                except (ValueError, IndexError):
                    valid = False
                if not valid:
                    invalid_labels.append(f"{label_path}:{line_number}")
                    continue
                class_counts[class_id] += 1
                box_count += 1
        split_stats[split] = {
            "images": len(images),
            "labels": len(labels),
            "boxes": box_count,
            "images_without_label": sorted(set(images) - set(labels)),
            "labels_without_image": sorted(set(labels) - set(images)),
        }
    result = {
        "dataset_path": Path(os.path.relpath(dataset, ROOT)).as_posix(),
        "license": "AGPL-3.0",
        "classes": CLASSES,
        "splits": split_stats,
        "class_box_counts": {CLASSES[index]: class_counts[index] for index in range(len(CLASSES))},
        "image_count": sum(item["images"] for item in split_stats.values()),
        "box_count": sum(item["boxes"] for item in split_stats.values()),
        "invalid_labels": invalid_labels,
    }
    if invalid_labels:
        raise ValueError(f"发现 {len(invalid_labels)} 行无效标注，请先修复")
    return result


def write_dataset_yaml(dataset: Path) -> Path:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    path = GENERATED_DIR / "dataset.yaml"
    payload = {
        "path": dataset.as_posix(),
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "names": dict(enumerate(CLASSES)),
    }
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def _metrics(source) -> dict[str, float]:
    return {key: float(value) for key, value in source.results_dict.items()}


def train(
    dataset: Path, epochs: int, device: str | None, image_size: int, batch: int,
    base_model: str, evaluate_test: bool = False,
) -> dict:
    from ultralytics import YOLO

    audit = audit_dataset(dataset)
    dataset_yaml = write_dataset_yaml(dataset)
    model = YOLO(base_model)
    result = model.train(
        data=str(dataset_yaml), epochs=epochs, imgsz=image_size, batch=batch,
        workers=0, device=device, project=str(MODEL_DIR / "training_runs"),
        name=f"safety_ppe_{Path(base_model).stem}", exist_ok=True, seed=42, deterministic=True, plots=True,
        patience=10, pretrained=True, optimizer="AdamW", lr0=0.001, lrf=0.01,
        weight_decay=0.0005, warmup_epochs=3, cos_lr=True, degrees=10.0,
        translate=0.1, scale=0.5, fliplr=0.5, mosaic=1.0, mixup=0.1,
    )
    best = Path(result.save_dir) / "weights" / "best.pt"
    if not best.exists():
        raise FileNotFoundError("训练完成但未找到 best.pt")
    trained = YOLO(str(best))
    validation_metrics = trained.val(data=str(dataset_yaml), split="val", device=device, workers=0, imgsz=image_size)
    test_metrics = (
        trained.val(data=str(dataset_yaml), split="test", device=device, workers=0, imgsz=image_size)
        if evaluate_test else None
    )
    target = MODEL_DIR / "safety_ppe_yolo.pt"
    variant_target = MODEL_DIR / f"safety_ppe_{Path(base_model).stem}.pt"
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best, target)
    shutil.copy2(best, variant_target)
    summary = {
        "trained_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "base_model": base_model,
        "baseline_reference": "https://github.com/vamsiprasanth/constructionsafety",
        "weights": target.relative_to(ROOT).as_posix(),
        "variant_weights": variant_target.relative_to(ROOT).as_posix(),
        "epochs": epochs,
        "image_size": image_size,
        "batch": batch,
        "device": device or "auto",
        "optimizer": "AdamW",
        "patience": 10,
        "cos_lr": True,
        "checkpoint_selection": "best_validation_checkpoint",
        "test_evaluation_requested": evaluate_test,
        "dataset": audit,
        "dataset_yaml_sha256": hashlib.sha256(dataset_yaml.read_bytes()).hexdigest(),
        "validation_metrics": _metrics(validation_metrics),
        "test_metrics": _metrics(test_metrics) if test_metrics else None,
        "experiment_protocol": "模型与阈值仅依据验证集选择；独立测试仅在最终模型冻结后执行一次",
        "business_classes": ["Person", "helmet", "vest", "no_helmet"],
        "scope": "安全监管独立模型；仅明确检测到 no_helmet 时生成未戴安全帽风险",
    }
    summary_text = json.dumps(summary, ensure_ascii=False, indent=2)
    (MODEL_DIR / "safety_ppe_training_summary.json").write_text(summary_text, encoding="utf-8")
    (MODEL_DIR / f"safety_ppe_training_summary_{Path(base_model).stem}.json").write_text(
        summary_text, encoding="utf-8"
    )
    return summary


if __name__ == "__main__":
    configure_console()
    parser = argparse.ArgumentParser(description="校验或训练施工安全监管独立模型")
    parser.add_argument("--data", help="construction-ppe 数据集目录；默认自动查找")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--device", default=None, help="例如 0 或 cpu；默认自动选择")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--model", choices=["yolov8n.pt", "yolov8s.pt"], default="yolov8n.pt")
    parser.add_argument("--evaluate-test", action="store_true", help="仅最终模型冻结时启用一次")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    source = find_dataset(args.data)
    checked = audit_dataset(source)
    if args.check_only:
        print(json.dumps(checked, ensure_ascii=False, indent=2))
    else:
        if args.epochs < 1:
            raise ValueError("训练轮数必须至少为 1")
        print(json.dumps(
            train(source, args.epochs, args.device, args.imgsz, args.batch, args.model, args.evaluate_test),
            ensure_ascii=False, indent=2,
        ))
