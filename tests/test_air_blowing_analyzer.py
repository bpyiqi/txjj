import json
from pathlib import Path

from backend.app.air_blowing_analyzer import (
    CONSTRUCTION_ENVIRONMENT,
    PROJECT_TYPE,
    SCENE,
    STAGES,
    TARGET_OBJECTS,
    analyze_profiles,
)


ROOT = Path(__file__).resolve().parents[1]


def test_cross_video_construction_evidence_contract():
    result = analyze_profiles(ROOT / "demo_air_blowing" / "video_profiles.json", ROOT)
    assert result["scene"] == SCENE
    assert result["project_type"] == PROJECT_TYPE
    assert result["construction_environment"] == CONSTRUCTION_ENVIRONMENT
    assert result["summary"]["video_count"] == 2
    assert result["summary"]["sample_count"] == 16
    assert set(result["summary"]["covered_stages"]) == set(STAGES)
    assert set(result["summary"]["covered_objects"]) == TARGET_OBJECTS
    assert result["summary"]["stage_accuracy"] == 0.9375
    for record in result["evidence"]:
        for required in (
            "video_id", "timestamp", "frame_path", "detected_objects",
            "construction_stage", "confidence", "risk_detection", "engineering_object",
            "acceptance_rule",
        ):
            assert required in record
        assert (ROOT / record["frame_path"]).exists()
        assert len(record["frame_sha256"]) == 64
        assert record["acceptance_rule"]["rule_id"].startswith("EXP-FOC-")
        assert 0 <= record["confidence"] <= 1


def test_generated_json_matches_contract():
    path = ROOT / "demo_air_blowing" / "output" / "construction_evidence.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["summary"]["stage_accuracy"] == 0.9375
    assert len(payload["evidence"]) == 16
