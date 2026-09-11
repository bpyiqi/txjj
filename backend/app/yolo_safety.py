from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2

from .database import BASE_DIR


MODEL_PATH = BASE_DIR / "models" / "safety_ppe_yolo.pt"
SUMMARY_PATH = BASE_DIR / "models" / "safety_ppe_training_summary.json"
CLASS_MAP = {
    "Person": "worker",
    "helmet": "safety_helmet",
    "vest": "safety_vest",
    "no_helmet": "no_safety_helmet",
}
CONFIDENCE_THRESHOLD = 0.35
_cached_model: Any = None
_cached_mtime: int | None = None


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
        "classes": list(CLASS_MAP.values()),
        "training": summary,
        "runtime_error": runtime_error,
    }


def _model():
    global _cached_model, _cached_mtime
    if not MODEL_PATH.exists():
        _cached_model = None
        _cached_mtime = None
        return None
    mtime = MODEL_PATH.stat().st_mtime_ns
    if _cached_model is not None and _cached_mtime == mtime:
        return _cached_model
    try:
        from ultralytics import YOLO
        _cached_model = YOLO(str(MODEL_PATH))
        _cached_mtime = mtime
    except Exception:
        _cached_model = None
        _cached_mtime = None
    return _cached_model


def detect_at_timestamps(video_path: Path, timestamps: list[float], confidence: float = CONFIDENCE_THRESHOLD) -> dict[str, Any]:
    model = _model()
    if model is None:
        return {"enabled": False, "frames": [], "detection_count": 0, "risk_count": 0}
    capture = cv2.VideoCapture(str(video_path))
    frames: list[dict[str, Any]] = []
    detection_count = 0
    risk_count = 0
    try:
        for timestamp in timestamps:
            capture.set(cv2.CAP_PROP_POS_MSEC, float(timestamp) * 1000)
            ok, frame = capture.read()
            detections: list[dict[str, Any]] = []
            risks: list[dict[str, Any]] = []
            if ok and frame is not None:
                result = model.predict(source=frame, conf=confidence, iou=0.45, max_det=50, verbose=False)[0]
                for box in result.boxes:
                    source_class = str(result.names[int(box.cls.item())])
                    label = CLASS_MAP.get(source_class)
                    if not label:
                        continue
                    score = float(box.conf.item())
                    item = {
                        "label": label,
                        "source_class": source_class,
                        "confidence": round(score, 4),
                        "bbox_xyxy": [round(float(value), 1) for value in box.xyxy[0].tolist()],
                    }
                    detections.append(item)
                    if source_class == "no_helmet":
                        risks.append({
                            "risk": "safety_helmet_missing",
                            "severity": "high",
                            "status": "detected",
                            "confidence": round(score, 4),
                            "bbox_xyxy": item["bbox_xyxy"],
                        })
            detection_count += len(detections)
            risk_count += len(risks)
            frames.append({"timestamp": timestamp, "detections": detections, "risks": risks})
    finally:
        capture.release()
    return {
        "enabled": True,
        "frames": frames,
        "detection_count": detection_count,
        "risk_count": risk_count,
    }


def merge_safety_detections(records: list[dict[str, Any]], video_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    result = detect_at_timestamps(video_path, [float(record["timestamp"]) for record in records])
    if not result["enabled"]:
        return records, result
    by_time = {round(float(item["timestamp"]), 3): item for item in result["frames"]}
    for record in records:
        frame = by_time.get(round(float(record["timestamp"]), 3), {"detections": [], "risks": []})
        record.setdefault("detected_objects", []).extend(frame["detections"])
        record.setdefault("risk_detection", []).extend(frame["risks"])
    return records, result
