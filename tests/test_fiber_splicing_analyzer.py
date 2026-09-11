import hashlib
import json
from pathlib import Path

from backend.app.fiber_splicing_analyzer import SCENE, STAGES, TARGET_OBJECTS, analyze_profile


ROOT = Path(__file__).resolve().parents[1]


def test_fiber_splicing_evidence_contract():
    evidence, metrics = analyze_profile(
        ROOT / "demo_air_blowing" / "fiber_splicing_profile.json", ROOT
    )
    assert metrics["scene"] == SCENE
    assert metrics["sample_count"] == 9
    assert set(metrics["covered_stages"]) == set(STAGES)
    assert metrics["stage_accuracy"] == 1.0
    assert metrics["missing_target_objects"] == ["splice_tray"]
    assert set(metrics["covered_objects"]) == TARGET_OBJECTS - {"splice_tray"}
    for item in evidence:
        assert set(item) == {
            "video_id", "timestamp", "stage", "detected_objects", "confidence", "evidence_hash"
        }
        assert len(item["evidence_hash"]) == 64
        int(item["evidence_hash"], 16)
        assert 0 <= item["confidence"] <= 1


def test_generated_fiber_splicing_json():
    path = ROOT / "demo_air_blowing" / "output" / "fiber_splicing_evidence.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert len(payload) == 9
    assert {item["stage"] for item in payload} == set(STAGES)
    assert hashlib.sha256(path.read_bytes()).hexdigest()

