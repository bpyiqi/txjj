from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import cv2

from .database import BASE_DIR


MODEL_PATH = BASE_DIR / "models" / "construction_yolo.pt"
SUMMARY_PATH = BASE_DIR / "models" / "training_summary.json"
TARGET_CLASSES = {"blowing_machine", "cable_reel", "fusion_splicer"}
CLASS_THRESHOLDS = {"blowing_machine": 0.025, "cable_reel": 0.015, "fusion_splicer": 0.08}


def model_status() -> dict[str, Any]:
    runtime_error = None
    try:
        import ultralytics
        package_version = ultralytics.__version__
    except Exception as exc:
        package_version = None
        runtime_error = f"{type(exc).__name__}: {exc}"
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8")) if SUMMARY_PATH.exists() else None
    return {
        "runtime_available": package_version is not None,
        "runtime_version": package_version,
        "weights_available": MODEL_PATH.exists(),
        "classes": sorted(TARGET_CLASSES),
        "training": summary,
        "runtime_error": runtime_error,
    }


@lru_cache(maxsize=1)
def _model():
    if not MODEL_PATH.exists():
        return None
    try:
        from ultralytics import YOLO
    except Exception:
        return None
    return YOLO(str(MODEL_PATH))


def infer_scene(detections: list[dict[str, Any]]) -> str | None:
    labels = {item["label"] for item in detections}
    if "fusion_splicer" in labels:
        return "fusion_splicing"
    if labels & {"blowing_machine", "cable_reel"}:
        return "air_blowing"
    return None


def detect_at_timestamps(video_path: Path, timestamps: list[float], confidence: float | None = None) -> dict[str, Any]:
    model = _model()
    if model is None:
        return {"enabled": False, "scene": None, "frames": []}
    capture = cv2.VideoCapture(str(video_path))
    frames = []
    all_detections = []
    try:
        for timestamp in timestamps:
            capture.set(cv2.CAP_PROP_POS_MSEC, float(timestamp) * 1000)
            ok, frame = capture.read()
            if not ok or frame is None:
                frames.append({"timestamp": timestamp, "detections": []})
                continue
            result = model.predict(source=frame, conf=confidence or min(CLASS_THRESHOLDS.values()), iou=0.45, max_det=20, verbose=False)[0]
            detections = []
            for box in result.boxes:
                class_id = int(box.cls.item())
                label = str(result.names[class_id])
                if label not in TARGET_CLASSES:
                    continue
                score = float(box.conf.item())
                if score < (confidence if confidence is not None else CLASS_THRESHOLDS[label]):
                    continue
                item = {
                    "label": label,
                    "confidence": round(score, 4),
                    "bbox_xyxy": [round(float(value), 1) for value in box.xyxy[0].tolist()],
                }
                detections.append(item)
                all_detections.append(item)
            frames.append({"timestamp": timestamp, "detections": detections})
    finally:
        capture.release()
    return {"enabled": True, "scene": infer_scene(all_detections), "frames": frames}


def merge_detections(records: list[dict[str, Any]], video_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    result = detect_at_timestamps(video_path, [float(record["timestamp"]) for record in records])
    if not result["enabled"]:
        return records, result
    by_time = {round(float(item["timestamp"]), 3): item["detections"] for item in result["frames"]}
    for record in records:
        existing = [item for item in record.get("detected_objects", []) if item.get("label") not in TARGET_CLASSES]
        record["detected_objects"] = existing + by_time.get(round(float(record["timestamp"]), 3), [])
    return records, result
