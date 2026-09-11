"""Lightweight Fiber Fusion Splicing verification demo.

This module is deliberately independent from ``main.py`` so all existing
HTTP interfaces remain unchanged. The bundled profile contains manually
reviewed domain-object observations; the temporal rule model assigns stages.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .video_sampling import read_key_frames, write_jpeg


SCENE = "fiber_splicing"
STAGES = (
    "fiber_stripping",
    "fiber_cleaning",
    "fiber_cleaving",
    "fusion_splicing",
    "fiber_organizing",
)
TARGET_OBJECTS = {
    "fusion_splicer",
    "fiber",
    "splice_tray",
    "protection_sleeve",
    "technician",
}


@dataclass(frozen=True)
class Detection:
    label: str
    confidence: float
    source: str = "reviewed_domain_profile"

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


def infer_stage(detections: Iterable[Detection], progress: float) -> tuple[str, float]:
    """Infer one of five splicing stages from object evidence and video time."""
    labels = {item.label for item in detections}
    anchors = {
        "fiber_stripping": 0.16,
        "fiber_cleaning": 0.30,
        "fiber_cleaving": 0.40,
        "fusion_splicing": 0.58,
        "fiber_organizing": 0.84,
    }
    scores = {stage: max(0.0, 1.0 - abs(progress - anchor) * 5.0) for stage, anchor in anchors.items()}
    scores["fiber_stripping"] += 0.25 * ("technician" in labels and "fiber" in labels)
    scores["fiber_cleaning"] += 0.2 * ("technician" in labels and "fiber" in labels)
    scores["fiber_cleaving"] += 0.2 * ("technician" in labels and "fiber" in labels)
    scores["fusion_splicing"] += 0.8 * ("fusion_splicer" in labels)
    scores["fiber_organizing"] += 0.8 * ("protection_sleeve" in labels or "splice_tray" in labels)
    scores["fiber_organizing"] += 0.4 if progress >= 0.78 else 0.0
    stage = max(STAGES, key=lambda item: scores[item])
    ordered = sorted(scores.values(), reverse=True)
    margin = ordered[0] - ordered[1]
    confidence = min(0.97, 0.66 + margin * 0.12 + min(0.18, len(labels) * 0.045))
    return stage, round(confidence, 3)


def evidence_hash(video_sha256: str, record: dict[str, Any]) -> str:
    """Hash the source-video identity and canonical evidence payload."""
    canonical = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{video_sha256}:{canonical}".encode("utf-8")).hexdigest()


def analyze_profile(profile_path: Path, project_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    video_path = project_root / profile["video_path"]
    if not video_path.exists():
        raise FileNotFoundError(video_path)
    video_hash = sha256_file(video_path)
    duration = float(profile["duration_seconds"])
    output: list[dict[str, Any]] = []
    correct = 0

    for sample in profile["samples"]:
        detections = [Detection(**item) for item in sample["detected_objects"]]
        stage, confidence = infer_stage(detections, float(sample["timestamp"]) / duration)
        core = {
            "video_id": profile["video_id"],
            "timestamp": float(sample["timestamp"]),
            "stage": stage,
            "detected_objects": [item.as_dict() for item in detections],
            "confidence": confidence,
        }
        output.append({**core, "evidence_hash": evidence_hash(video_hash, core)})
        correct += stage == sample["ground_truth_stage"]

    metrics = {
        "scene": SCENE,
        "video_id": profile["video_id"],
        "title": profile["title"],
        "source_url": profile["source_url"],
        "video_path": profile["video_path"],
        "video_sha256": video_hash,
        "sample_count": len(output),
        "correct_stage_count": correct,
        "stage_accuracy": round(correct / len(output), 4) if output else 0.0,
        "covered_stages": sorted({item["stage"] for item in output}),
        "covered_objects": sorted({obj["label"] for item in output for obj in item["detected_objects"]}),
        "missing_target_objects": sorted(TARGET_OBJECTS - {obj["label"] for item in output for obj in item["detected_objects"]}),
        "review_note": "目标为人工复核领域标注；工序由轻量时序规则推断。splice_tray 未在视频中清晰出现。",
    }
    return output, metrics


def analyze_video_with_opencv(
    video_path: Path,
    output_dir: Path,
    video_id: str,
    sample_count: int = 9,
) -> list[dict[str, Any]]:
    """Extract key frames and produce reviewable splicing-stage evidence."""
    output_dir.mkdir(parents=True, exist_ok=True)
    frames = read_key_frames(video_path, sample_count)
    video_hash = sha256_file(video_path)
    records: list[dict[str, Any]] = []
    for index, (timestamp, frame) in enumerate(frames):
        progress = (index + 0.5) / len(frames)
        frame_path = output_dir / f"frame_{index + 1:03d}_{int(timestamp * 1000):08d}ms.jpg"
        write_jpeg(frame, frame_path)
        stage = STAGES[min(int(progress * len(STAGES)), len(STAGES) - 1)]
        core = {
            "video_id": video_id,
            "timestamp": round(timestamp, 3),
            "stage": stage,
            "detected_objects": [],
            "confidence": 0.5,
        }
        records.append({
            **core,
            "frame_path": frame_path.as_posix(),
            "evidence_hash": evidence_hash(video_hash, core),
            "analysis_basis": "施工任务类型与视频时序分段",
            "review_status": "待人工复核",
        })
    return records
