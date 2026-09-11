from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "datasets" / "challenge_video_construction"
MODEL = ROOT / "backend" / "models" / "construction_yolo.pt"
TARGETS = {"blowing_machine": 0, "cable_reel": 1, "fusion_splicer": 2}
THRESHOLDS = {"blowing_machine": 0.025, "cable_reel": 0.015, "fusion_splicer": 0.08}


def prelabel() -> dict:
    from ultralytics import YOLO

    manifest = json.loads((DATASET / "annotation_manifest.json").read_text(encoding="utf-8"))
    model = YOLO(str(MODEL))
    counts = Counter()
    labeled_images = 0
    for item in manifest["images"]:
        image_path = ROOT / item["image_path"]
        frame = cv2.imdecode(np.frombuffer(image_path.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError(f"图片无法读取：{image_path}")
        result = model.predict(frame, conf=min(THRESHOLDS.values()), imgsz=320, iou=0.45, max_det=20, verbose=False)[0]
        rows = []
        for box in result.boxes:
            name = str(result.names[int(box.cls.item())])
            score = float(box.conf.item())
            if name not in TARGETS or score < THRESHOLDS[name]:
                continue
            cx, cy, width, height = (float(value) for value in box.xywhn[0].tolist())
            rows.append(f"{TARGETS[name]} {cx:.6f} {cy:.6f} {width:.6f} {height:.6f}")
            counts[name] += 1
        target = DATASET / "candidate_labels" / item["split"] / f"{item['id']}.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(("\n".join(rows) + "\n") if rows else "", encoding="utf-8")
        labeled_images += bool(rows)
    summary = {
        "status": "model_candidates_only_not_ground_truth",
        "model": str(MODEL),
        "images": len(manifest["images"]),
        "images_with_candidates": labeled_images,
        "candidate_boxes": sum(counts.values()),
        "class_counts": dict(counts),
        "output": str(DATASET / "candidate_labels"),
    }
    (DATASET / "candidate_labels" / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


if __name__ == "__main__":
    print(json.dumps(prelabel(), ensure_ascii=False, indent=2))
