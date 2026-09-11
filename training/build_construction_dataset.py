from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import cv2


ROOT = Path(__file__).resolve().parents[1]
ANNOTATIONS = ROOT / "training" / "reviewed_annotations.json"
DATASET = ROOT / "datasets" / "construction_objects"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _frame(video: Path, timestamp: float):
    capture = cv2.VideoCapture(str(video))
    capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
    ok, frame = capture.read()
    capture.release()
    if not ok or frame is None:
        raise RuntimeError(f"无法从视频提取 {timestamp:.1f}s 影像：{video.name}")
    return frame


def build_dataset() -> dict:
    spec = json.loads(ANNOTATIONS.read_text(encoding="utf-8"))
    classes = spec["classes"]
    class_ids = {name: index for index, name in enumerate(classes)}
    if DATASET.exists():
        shutil.rmtree(DATASET)
    for split in ("train", "val"):
        (DATASET / "images" / split).mkdir(parents=True)
        (DATASET / "labels" / split).mkdir(parents=True)

    manifest = {"classes": classes, "review_status": spec["review_status"], "samples": []}
    for sample in spec["samples"]:
        source = ROOT / sample["video"]
        timestamp = float(sample["timestamp"])
        split = sample["split"]
        stem = f"{source.stem}_{round(timestamp * 1000):07d}ms"
        image_path = DATASET / "images" / split / f"{stem}.jpg"
        label_path = DATASET / "labels" / split / f"{stem}.txt"
        frame = _frame(source, timestamp)
        height, width = frame.shape[:2]
        lines = []
        for box in sample["boxes"]:
            x1, y1, x2, y2 = map(float, box["xyxy"])
            if box["label"] not in class_ids or not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
                raise ValueError(f"无效标注：{source.name} {timestamp}s {box}")
            lines.append(
                f"{class_ids[box['label']]} {(x1+x2)/(2*width):.6f} {(y1+y2)/(2*height):.6f} "
                f"{(x2-x1)/width:.6f} {(y2-y1)/height:.6f}"
            )
        ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if not ok:
            raise RuntimeError(f"影像编码失败：{source.name} {timestamp}s")
        image_path.write_bytes(encoded.tobytes())
        label_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        manifest["samples"].append({
            "image": image_path.relative_to(ROOT).as_posix(),
            "source_video": sample["video"],
            "source_video_sha256": _sha256(source),
            "timestamp": timestamp,
            "stage": sample["stage"],
            "split": split,
            "box_count": len(lines),
            "frame_sha256": _sha256(image_path),
        })

    yaml = "path: datasets/construction_objects\ntrain: images/train\nval: images/val\nnames:\n" + "".join(
        f"  {index}: {name}\n" for index, name in enumerate(classes)
    )
    (DATASET / "dataset.yaml").write_text(yaml, encoding="utf-8")
    (DATASET / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "dataset": str(DATASET),
        "sample_count": len(manifest["samples"]),
        "train_count": sum(item["split"] == "train" for item in manifest["samples"]),
        "val_count": sum(item["split"] == "val" for item in manifest["samples"]),
        "box_count": sum(item["box_count"] for item in manifest["samples"]),
        "classes": classes,
    }


if __name__ == "__main__":
    print(json.dumps(build_dataset(), ensure_ascii=False, indent=2))
