from pathlib import Path

from backend.app import yolo_safety
from training.train_safety_yolo import audit_dataset, find_dataset


def test_construction_ppe_dataset_is_valid_and_complete():
    result = audit_dataset(find_dataset())
    assert result["image_count"] == 1416
    assert result["box_count"] == 11614
    assert result["invalid_labels"] == []
    assert result["class_box_counts"]["no_helmet"] == 485


def test_safety_results_merge_without_inventing_missing_equipment(monkeypatch):
    monkeypatch.setattr(yolo_safety, "detect_at_timestamps", lambda path, timestamps: {
        "enabled": True,
        "detection_count": 2,
        "risk_count": 1,
        "frames": [{
            "timestamp": timestamps[0],
            "detections": [
                {"label": "worker", "source_class": "Person", "confidence": 0.8, "bbox_xyxy": [1, 2, 3, 4]},
                {"label": "no_safety_helmet", "source_class": "no_helmet", "confidence": 0.7, "bbox_xyxy": [1, 2, 3, 4]},
            ],
            "risks": [{"risk": "safety_helmet_missing", "severity": "high", "confidence": 0.7}],
        }],
    })
    records, summary = yolo_safety.merge_safety_detections(
        [{"timestamp": 1.0, "detected_objects": [], "risk_detection": []}], Path("sample.mp4")
    )
    assert summary["risk_count"] == 1
    assert {item["label"] for item in records[0]["detected_objects"]} == {"worker", "no_safety_helmet"}
    assert records[0]["risk_detection"][0]["risk"] == "safety_helmet_missing"


def test_safety_model_status_is_truthful():
    status = yolo_safety.model_status()
    assert status["weights_available"] == Path("backend/models/safety_ppe_yolo.pt").exists()
    assert status["classes"] == ["worker", "safety_helmet", "safety_vest", "no_safety_helmet"]
