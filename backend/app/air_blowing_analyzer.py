"""Lightweight optical-cable air-blowing construction verification demo.

The existing platform API is intentionally untouched.  This module can be used
as a standalone CLI/service component and supports two backends:

1. pre-extracted, reviewed evidence frames (no extra runtime dependency);
2. OpenCV key-frame sampling and temporal stage segmentation for new videos.

The supplied demo profiles are transparent calibration/validation annotations,
not a replacement for a trained domain detector.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .video_sampling import read_key_frames, write_jpeg


STAGES = (
    "equipment_setup",
    "cable_loading",
    "blowing_process",
    "completion_check",
)

TARGET_OBJECTS = {
    "fiber_cable",
    "blowing_machine",
    "air_compressor",
    "worker",
    "cable_reel",
    "safety_helmet",
}

SCENE = "highway_communication_construction"
PROJECT_TYPE = "expressway_optical_cable_deployment"
CONSTRUCTION_ENVIRONMENT = "高速公路通信基础设施施工现场"

ACCEPTANCE_RULES = {
    "equipment_setup": {
        "rule_id": "EXP-FOC-001",
        "name": "吹缆设备进场与安全布设",
        "required_evidence": ["blowing_machine", "air_compressor", "worker"],
    },
    "cable_loading": {
        "rule_id": "EXP-FOC-002",
        "name": "光缆盘与入缆准备检查",
        "required_evidence": ["fiber_cable", "cable_reel"],
    },
    "blowing_process": {
        "rule_id": "EXP-FOC-003",
        "name": "气吹敷设施工过程留痕",
        "required_evidence": ["fiber_cable", "blowing_machine"],
    },
    "completion_check": {
        "rule_id": "EXP-FOC-004",
        "name": "敷设完成与现场复核",
        "required_evidence": ["fiber_cable", "worker"],
    },
}


@dataclass(frozen=True)
class Detection:
    label: str
    confidence: float
    source: str = "domain_demo_profile"

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "confidence": round(float(self.confidence), 3),
            "source": self.source,
        }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def infer_stage(detections: Iterable[Detection], progress: float) -> tuple[str, float, dict[str, float]]:
    """Infer a stage from detected domain objects and normalized video time."""
    labels = {item.label for item in detections}
    scores = {stage: 0.05 for stage in STAGES}

    scores["equipment_setup"] += 1.2 * ("air_compressor" in labels)
    scores["equipment_setup"] += 0.9 * ("blowing_machine" in labels)
    scores["equipment_setup"] += 0.4 * ("worker" in labels)
    scores["equipment_setup"] += 0.9 if progress <= 0.18 else 0.0

    scores["cable_loading"] += 1.3 * ("cable_reel" in labels)
    scores["cable_loading"] += 0.7 * ("fiber_cable" in labels)
    scores["cable_loading"] += 0.4 * ("worker" in labels)
    scores["cable_loading"] += 0.3 if progress <= 0.45 else 0.0

    scores["blowing_process"] += 1.3 * ("blowing_machine" in labels)
    scores["blowing_process"] += 1.0 * ("fiber_cable" in labels)
    scores["blowing_process"] += 0.4 * ("air_compressor" in labels)
    scores["blowing_process"] += 0.5 if 0.18 < progress < 0.85 else 0.0

    scores["completion_check"] += 0.4 * ("fiber_cable" in labels)
    scores["completion_check"] += 0.3 * ("worker" in labels)
    scores["completion_check"] += 2.5 if progress >= 0.75 else 0.0
    scores["completion_check"] += 0.5 if progress >= 0.9 else 0.0

    stage = max(STAGES, key=lambda name: scores[name])
    ordered = sorted(scores.values(), reverse=True)
    margin = ordered[0] - ordered[1]
    object_support = min(1.0, len(labels & TARGET_OBJECTS) / 4.0)
    confidence = min(0.97, 0.58 + margin * 0.08 + object_support * 0.2)
    return stage, round(confidence, 3), {key: round(value, 3) for key, value in scores.items()}


def detect_risks(stage: str, detections: Iterable[Detection], annotated: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    labels = {item.label for item in detections}
    risks = list(annotated or [])
    if "worker" in labels and "safety_helmet" not in labels:
        risks.append({
            "risk": "safety_helmet_not_confirmed",
            "severity": "high",
            "confidence": 0.72,
            "status": "manual_review_required",
        })
    if stage == "blowing_process" and "blowing_machine" not in labels:
        risks.append({
            "risk": "blowing_machine_not_visible",
            "severity": "medium",
            "confidence": 0.66,
            "status": "evidence_gap",
        })
    if stage == "completion_check" and "worker" not in labels:
        risks.append({
            "risk": "completion_check_not_fully_observed",
            "severity": "medium",
            "confidence": 0.7,
            "status": "evidence_gap",
        })
    return risks


def analyze_profile(profile: dict[str, Any], project_root: Path) -> dict[str, Any]:
    video_path = project_root / profile["video_path"]
    if not video_path.exists():
        raise FileNotFoundError(video_path)
    records: list[dict[str, Any]] = []
    duration = float(profile["duration_seconds"])
    engineering_object = profile["engineering_object"]

    for sample in profile["samples"]:
        frame_path = project_root / sample["frame_path"]
        if not frame_path.exists():
            raise FileNotFoundError(frame_path)
        detections = [Detection(**item) for item in sample["detected_objects"]]
        timestamp = float(sample["timestamp"])
        stage, confidence, scores = infer_stage(detections, timestamp / duration)
        records.append({
            "video_id": profile["video_id"],
            "timestamp": timestamp,
            "frame_path": frame_path.relative_to(project_root).as_posix(),
            "frame_sha256": sha256_file(frame_path),
            "detected_objects": [item.as_dict() for item in detections],
            "construction_stage": stage,
            "confidence": confidence,
            "risk_detection": detect_risks(stage, detections, sample.get("risk_detection")),
            "engineering_object": engineering_object,
            "acceptance_rule": ACCEPTANCE_RULES[stage],
            "scene": SCENE,
            "project_type": PROJECT_TYPE,
            "construction_environment": CONSTRUCTION_ENVIRONMENT,
            "stage_scores": scores,
            "ground_truth_stage": sample.get("ground_truth_stage"),
            "review_status": "人工抽样复核",
        })

    correct = sum(item["construction_stage"] == item["ground_truth_stage"] for item in records)
    return {
        "video_id": profile["video_id"],
        "title": profile["title"],
        "source_url": profile["source_url"],
        "duration_seconds": duration,
        "video_path": profile["video_path"],
        "video_sha256": sha256_file(video_path),
        "sample_count": len(records),
        "correct_stage_count": correct,
        "stage_accuracy": round(correct / len(records), 4) if records else 0.0,
        "evidence": records,
    }


def analyze_profiles(profile_path: Path, project_root: Path) -> dict[str, Any]:
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    videos = [analyze_profile(profile, project_root) for profile in payload["videos"]]
    evidence = [record for video in videos for record in video["evidence"]]
    correct = sum(video["correct_stage_count"] for video in videos)
    return {
        "schema_version": "construction-evidence/1.0",
        "system_name": "面向高速公路通信基础设施建设的光缆敷设施工智能监管与可信交付系统",
        "scene": SCENE,
        "project_type": PROJECT_TYPE,
        "construction_environment": CONSTRUCTION_ENVIRONMENT,
        "application_value": [
            "通信基础设施施工过程监管",
            "隐蔽工程影像验真",
            "竣工数字档案生成",
        ],
        "model": {
            "name": "AirBlowing-Hybrid-Demo",
            "version": "1.0.0",
            "backend": "reviewed-domain-detections + temporal-rule-engine",
            "optional_backend": "OpenCV关键影像提取",
            "limitations": "已复核样例提供领域目标标注；其他视频仅进行关键影像提取和时序分段，施工对象需人工复核。",
        },
        "summary": {
            "video_count": len(videos),
            "sample_count": len(evidence),
            "correct_stage_count": correct,
            "stage_accuracy": round(correct / len(evidence), 4) if evidence else 0.0,
            "covered_stages": sorted({item["construction_stage"] for item in evidence}),
            "covered_objects": sorted({obj["label"] for item in evidence for obj in item["detected_objects"]}),
            "efficiency_estimate": {
                "basis": "Demo估算：人工逐帧整理5分钟/帧，AI辅助复核0.5分钟/帧",
                "manual_minutes": round(len(evidence) * 5.0, 1),
                "ai_assisted_minutes": round(len(evidence) * 0.5, 1),
                "time_reduction_rate": 0.9,
            },
        },
        "videos": [{key: value for key, value in video.items() if key != "evidence"} for video in videos],
        "evidence": evidence,
    }


def analyze_video_with_opencv(
    video_path: Path,
    output_dir: Path,
    video_id: str,
    engineering_object: dict[str, Any],
    sample_count: int = 8,
) -> list[dict[str, Any]]:
    """Extract key frames and produce reviewable temporal-stage evidence."""
    output_dir.mkdir(parents=True, exist_ok=True)
    frames = read_key_frames(video_path, sample_count)
    records: list[dict[str, Any]] = []
    for index, (timestamp, frame) in enumerate(frames):
        progress = (index + 0.5) / len(frames)
        frame_path = output_dir / f"frame_{index + 1:03d}_{int(timestamp * 1000):08d}ms.jpg"
        write_jpeg(frame, frame_path)
        stage = STAGES[min(int(progress * len(STAGES)), len(STAGES) - 1)]
        records.append({
            "video_id": video_id,
            "timestamp": round(timestamp, 3),
            "frame_path": frame_path.as_posix(),
            "frame_sha256": sha256_file(frame_path),
            "detected_objects": [],
            "construction_stage": stage,
            "confidence": 0.5,
            "risk_detection": [],
            "engineering_object": engineering_object,
            "acceptance_rule": ACCEPTANCE_RULES[stage],
            "scene": SCENE,
            "project_type": PROJECT_TYPE,
            "construction_environment": CONSTRUCTION_ENVIRONMENT,
            "stage_scores": {name: 1.0 if name == stage else 0.0 for name in STAGES},
            "analysis_basis": "施工任务类型与视频时序分段",
            "review_status": "待人工复核",
        })
    return records
