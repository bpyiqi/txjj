import json
from pathlib import Path

import pytest

from training.evaluate_safety_business import metrics


def test_business_metrics_are_calculated_from_counts():
    result = metrics(tp=8, fp=2, fn=2, tn=8)
    assert result["accuracy"] == 0.8
    assert result["precision"] == 0.8
    assert result["recall"] == 0.8
    assert result["f1"] == pytest.approx(0.8)


def test_new_video_split_is_source_isolated():
    manifest = json.loads(Path("datasets/challenge_video_construction/annotation_manifest.json").read_text(encoding="utf-8"))
    holdout = manifest["holdout_video"]
    assert manifest["classes"] == ["blowing_machine", "cable_reel", "fusion_splicer"]
    assert sum(item["split"] == "train" for item in manifest["images"]) == 167
    assert sum(item["split"] == "test" for item in manifest["images"]) == 116
    assert all(Path(item["source_video"]).name != holdout for item in manifest["images"] if item["split"] == "train")
    assert all(Path(item["source_video"]).name == holdout for item in manifest["images"] if item["split"] == "test")
