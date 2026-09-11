from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from build_video_training_dataset import EXPANDED, ROOT


WORKER_CLASS_ID = 6


def create(model_path: Path, confidence: float, imgsz: int, max_det: int) -> dict:
    from ultralytics import YOLO

    manifest = json.loads((EXPANDED / "annotation_manifest.json").read_text(encoding="utf-8"))
    model = YOLO(str(model_path))
    output_root = EXPANDED / "auto_labels"
    output_root.mkdir(parents=True, exist_ok=True)
    image_count = 0
    box_count = 0
    split_counts = Counter()
    confidence_values: list[float] = []
    for item in manifest["images"]:
        manual = ROOT / item["label_path"]
        if manual.exists() and manual.read_text(encoding="utf-8").strip():
            continue
        result = model.predict(
            source=str(ROOT / item["image_path"]),
            conf=confidence,
            imgsz=imgsz,
            classes=[0],
            max_det=max_det,
            iou=0.45,
            verbose=False,
        )[0]
        lines = []
        for box, score in zip(result.boxes.xywhn.cpu(), result.boxes.conf.cpu()):
            values = [float(value) for value in box.tolist()]
            lines.append("{} {:.6f} {:.6f} {:.6f} {:.6f}".format(WORKER_CLASS_ID, *values))
            confidence_values.append(float(score))
        target = output_root / item["split"] / f"{item['id']}.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        if lines:
            target.write_text("\n".join(lines) + "\n", encoding="utf-8")
            image_count += 1
            box_count += len(lines)
            split_counts[item["split"]] += 1
        elif target.exists():
            target.unlink()

    summary = {
        "model": str(model_path),
        "source_class": "person",
        "target_class": "worker",
        "target_class_id": WORKER_CLASS_ID,
        "confidence": confidence,
        "imgsz": imgsz,
        "max_det": max_det,
        "candidate_images": image_count,
        "candidate_boxes": box_count,
        "split_images": dict(split_counts),
        "mean_confidence": sum(confidence_values) / len(confidence_values) if confidence_values else None,
        "status": "candidate_only_not_manual_truth",
        "output": str(output_root),
    }
    (output_root / "worker_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create conservative worker candidates from COCO person detections")
    parser.add_argument("--model", type=Path, default=ROOT / "yolo26n.pt")
    parser.add_argument("--confidence", type=float, default=0.55)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--max-det", type=int, default=20)
    args = parser.parse_args()
    print(json.dumps(create(args.model, args.confidence, args.imgsz, args.max_det), ensure_ascii=False, indent=2))
