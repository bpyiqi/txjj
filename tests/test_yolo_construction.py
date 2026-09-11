import json
from pathlib import Path

from backend.app.yolo_construction import infer_scene, model_status
from training.build_construction_dataset import DATASET, build_dataset


def test_reviewed_dataset_builds_for_all_target_classes():
    result = build_dataset()
    assert result["sample_count"] == 16
    assert result["box_count"] == 22
    assert result["classes"] == ["blowing_machine", "cable_reel", "fusion_splicer"]
    assert len(list((DATASET / "images" / "train").glob("*.jpg"))) == 13
    assert len(list((DATASET / "images" / "val").glob("*.jpg"))) == 3
    manifest = json.loads((DATASET / "manifest.json").read_text(encoding="utf-8"))
    assert all(len(item["source_video_sha256"]) == 64 for item in manifest["samples"])


def test_scene_is_derived_from_yolo_target_labels():
    assert infer_scene([{"label": "blowing_machine"}]) == "air_blowing"
    assert infer_scene([{"label": "cable_reel"}]) == "air_blowing"
    assert infer_scene([{"label": "fusion_splicer"}]) == "fusion_splicing"
    assert infer_scene([]) is None


def test_model_status_is_truthful():
    status = model_status()
    assert status["weights_available"] == Path("backend/models/construction_yolo.pt").exists()
    assert status["classes"] == ["blowing_machine", "cable_reel", "fusion_splicer"]
