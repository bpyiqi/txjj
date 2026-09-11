from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from build_video_training_dataset import CLASSES, EXPANDED, ROOT


def auto_label(model_path: Path, confidence: float, imgsz: int, limit: int | None = None) -> dict:
    from ultralytics import YOLO

    manifest = json.loads((EXPANDED / "annotation_manifest.json").read_text(encoding="utf-8"))
    model = YOLO(str(model_path))
    output_root = EXPANDED / "auto_labels"
    output_root.mkdir(parents=True, exist_ok=True)
    counts = Counter()
    labeled_images = 0
    candidate_count = 0
    skipped = 0
    for item in manifest["images"]:
        manual = ROOT / item["label_path"]
        if manual.exists() and manual.read_text(encoding="utf-8").strip():
            continue
        if limit is not None and labeled_images >= limit:
            break
        image_path = ROOT / item["image_path"]
        result = model.predict(source=str(image_path), conf=confidence, imgsz=imgsz, iou=0.45, max_det=20, verbose=False)[0]
        lines = []
        for box, class_id, score in zip(result.boxes.xywhn.cpu(), result.boxes.cls.cpu(), result.boxes.conf.cpu()):
            class_id = int(class_id)
            if class_id >= len(CLASSES):
                skipped += 1
                continue
            values = [float(value) for value in box.tolist()]
            lines.append("{} {:.6f} {:.6f} {:.6f} {:.6f}".format(class_id, *values))
            counts[CLASSES[class_id]] += 1
            candidate_count += 1
        target = output_root / item["split"] / f"{item['id']}.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        if lines:
            target.write_text("\n".join(lines) + "\n", encoding="utf-8")
            labeled_images += 1
        elif target.exists():
            target.unlink()
    summary = {
        "model": str(model_path),
        "confidence": confidence,
        "imgsz": imgsz,
        "candidate_images": labeled_images,
        "candidate_boxes": candidate_count,
        "class_counts": dict(counts),
        "skipped_unknown_model_classes": skipped,
        "output": str(output_root),
        "status": "candidate_only_not_promoted",
    }
    (output_root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create model-assisted labels without overwriting manual labels")
    parser.add_argument("--model", type=Path, default=ROOT / "backend" / "models" / "construction_yolo_combined.pt")
    parser.add_argument("--confidence", type=float, default=0.55)
    parser.add_argument("--imgsz", type=int, default=320)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    print(json.dumps(auto_label(args.model, args.confidence, args.imgsz, args.limit), ensure_ascii=False, indent=2))
