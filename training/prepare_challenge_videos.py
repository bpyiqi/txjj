from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT.parents[1]
DATASET = ROOT / "datasets" / "challenge_video_construction"
HOLDOUT = "fd4737c5ce424df8061a4d8d2176d460.mp4"
CLASSES = ["blowing_machine", "cable_reel", "fusion_splicer"]
VIDEOS = {
    "1e7fb7bcca75a6da31224c7d5b74e0e4.mp4": ("air_blowing", 1.0, ["blowing_machine", "fiber_cable"]),
    "53d8f3cd412e0ec335240a774df4347e.mp4": ("air_blowing", 1.0, ["blowing_machine", "cable_reel"]),
    "a7bca6cab5b179999cc53d32f338e0dc.mp4": ("air_blowing", 1.0, ["blowing_machine", "fiber_cable"]),
    "bf96e1af8fd127a63d7ac96bc5d3a79c.mp4": ("fusion_splicing", 1.0, ["fusion_splicer"]),
    "d8807a35da0f027509584f9a97cb047c.mp4": ("fusion_splicing", 2.0, ["fusion_splicer", "splice_tray"]),
    HOLDOUT: ("air_blowing", 2.0, ["blowing_machine", "cable_reel"]),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare() -> dict:
    records = []
    video_records = []
    (DATASET / "images" / "val").mkdir(parents=True, exist_ok=True)
    (DATASET / "labels" / "val").mkdir(parents=True, exist_ok=True)
    for name, (scene, interval, suggestions) in VIDEOS.items():
        source = SOURCE_DIR / name
        if not source.exists():
            raise FileNotFoundError(source)
        source_hash = sha256(source)
        split = "test" if name == HOLDOUT else "train"
        image_dir = DATASET / "images" / split
        label_dir = DATASET / "labels" / split
        image_dir.mkdir(parents=True, exist_ok=True)
        label_dir.mkdir(parents=True, exist_ok=True)
        capture = cv2.VideoCapture(str(source))
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if not capture.isOpened() or fps <= 0 or frame_count <= 0:
            capture.release()
            raise ValueError(f"视频无法读取：{source}")
        duration = frame_count / fps
        last_kept = None
        extracted = 0
        for timestamp in np.arange(0, duration, interval):
            capture.set(cv2.CAP_PROP_POS_MSEC, float(timestamp) * 1000)
            ok, frame = capture.read()
            if not ok or frame is None:
                continue
            gray = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (96, 96))
            sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            difference = 255.0 if last_kept is None else float(cv2.absdiff(gray, last_kept).mean())
            if sharpness < 20 or difference < 1.8:
                continue
            last_kept = gray
            stem = f"{Path(name).stem}__{timestamp:07.2f}s"
            image_path = image_dir / f"{stem}.jpg"
            encoded, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
            if not encoded:
                raise OSError(f"图片写入失败：{image_path}")
            image_path.write_bytes(buffer.tobytes())
            records.append({
                "id": stem,
                "filename": image_path.name,
                "split": split,
                "source_dataset": "新增施工视频",
                "source_video": str(source),
                "source_video_sha256": source_hash,
                "timestamp": round(float(timestamp), 2),
                "phase": scene,
                "suggested_classes": suggestions,
                "image_sha256": sha256(image_path),
                "image_path": image_path.relative_to(ROOT).as_posix(),
                "label_path": (label_dir / f"{stem}.txt").relative_to(ROOT).as_posix(),
            })
            extracted += 1
        capture.release()
        video_records.append({
            "filename": name,
            "source_path": str(source),
            "sha256": source_hash,
            "scene": scene,
            "role": "independent_test" if split == "test" else "training_candidate",
            "duration_seconds": round(duration, 2),
            "sample_interval_seconds": interval,
            "extracted_frames": extracted,
        })
    payload = {
        "classes": CLASSES,
        "holdout_video": HOLDOUT,
        "split_policy": "按源视频隔离；保留视频及其帧只进入test，其他五段只进入train",
        "videos": video_records,
        "images": records,
    }
    DATASET.mkdir(parents=True, exist_ok=True)
    (DATASET / "annotation_manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (DATASET / "dataset.yaml").write_text(
        "# 使用 training/build_video_training_dataset.py 合并后训练；不要直接训练本文件。\n"
        f"path: {DATASET.as_posix()}\ntrain: images/train\nval: images/val\ntest: images/test\n\nnames:\n"
        + "".join(f"  {index}: {name}\n" for index, name in enumerate(CLASSES)),
        encoding="utf-8",
    )
    return {
        "dataset": str(DATASET),
        "holdout_video": HOLDOUT,
        "training_videos": len(VIDEOS) - 1,
        "train_frames": sum(item["split"] == "train" for item in records),
        "test_frames": sum(item["split"] == "test" for item in records),
        "videos": video_records,
    }


if __name__ == "__main__":
    print(json.dumps(prepare(), ensure_ascii=False, indent=2))
