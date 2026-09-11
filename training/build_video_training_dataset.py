from __future__ import annotations

import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "datasets" / "construction_objects"
EXPANDED = ROOT / "datasets" / "expanded_construction"
CHALLENGE = ROOT / "datasets" / "challenge_video_construction"
DATASET = ROOT / "datasets" / "video_construction_combined"

CLASSES = [
    "blowing_machine",
    "cable_reel",
    "fusion_splicer",
    "air_compressor",
    "fiber_cable",
    "splice_tray",
    "worker",
]

# The expanded annotation project has a ten-class vocabulary. Keep only the six
# classes that are currently supported by the video detector.
EXPANDED_CLASS_MAP = {0: 0, 1: 1, 2: 3, 3: 4, 4: 6, 5: 2, 7: 5}


def _copy_image(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists() or target.stat().st_size != source.stat().st_size:
        shutil.copy2(source, target)


def _read_yolo(source: Path, mapping: dict[int, int]) -> list[str]:
    rows = []
    for line in source.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 5:
            raise ValueError(f"Invalid YOLO row: {source}: {line}")
        old_id = int(parts[0])
        if old_id not in mapping:
            raise ValueError(f"Unsupported class {old_id} in {source}")
        rows.append(" ".join([str(mapping[old_id]), *parts[1:]]))
    return rows


def build(include_auto_worker: bool = False) -> dict:
    for split in ("train", "val", "test"):
        (DATASET / "images" / split).mkdir(parents=True, exist_ok=True)
        (DATASET / "labels" / split).mkdir(parents=True, exist_ok=True)

    records: list[dict] = []

    # The legacy set contains the 16 boxes that were already reviewed by hand.
    for split in ("train", "val"):
        for image in sorted((LEGACY / "images" / split).glob("*.jpg")):
            source_label = LEGACY / "labels" / split / f"{image.stem}.txt"
            if not source_label.exists():
                continue
            stem = f"legacy__{image.stem}"
            target_image = DATASET / "images" / split / f"{stem}.jpg"
            target_label = DATASET / "labels" / split / f"{stem}.txt"
            _copy_image(image, target_image)
            target_label.write_text("\n".join(_read_yolo(source_label, {0: 0, 1: 1, 2: 2})) + "\n", encoding="utf-8")
            records.append({
                "id": stem,
                "split": split,
                "source": "legacy_reviewed",
                "source_image": image.relative_to(ROOT).as_posix(),
                "source_label": source_label.relative_to(ROOT).as_posix(),
                "label_source": "manual_reviewed",
            })

    # Only non-empty hand labels from the expanded annotation workspace enter
    # the first training round. Auto labels are deliberately kept elsewhere.
    manifest = json.loads((EXPANDED / "annotation_manifest.json").read_text(encoding="utf-8"))
    for item in manifest["images"]:
        source_label = ROOT / item["label_path"]
        manual_text = source_label.read_text(encoding="utf-8").strip() if source_label.exists() else ""
        auto_label = EXPANDED / "auto_labels" / item["split"] / f"{item['id']}.txt"
        auto_text = auto_label.read_text(encoding="utf-8").strip() if auto_label.exists() else ""
        if not manual_text and not (include_auto_worker and auto_text):
            continue
        split = item["split"]
        stem = f"expanded__{item['id']}"
        target_image = DATASET / "images" / split / f"{stem}.jpg"
        target_label = DATASET / "labels" / split / f"{stem}.txt"
        _copy_image(ROOT / item["image_path"], target_image)
        if manual_text:
            lines = _read_yolo(source_label, EXPANDED_CLASS_MAP)
            label_source = "manual_annotation"
        else:
            lines = _read_yolo(auto_label, {6: 6})
            label_source = "auto_worker_assist"
        target_label.write_text("\n".join(lines) + "\n", encoding="utf-8")
        records.append({
            "id": stem,
            "split": split,
            "source": "expanded_dataset",
            "source_image": item["image_path"],
            "source_label": item["label_path"],
            "source_dataset": item["source_dataset"],
            "source_video": item.get("source_video", ""),
            "phase": item.get("phase", ""),
            "label_source": label_source,
        })

    # New videos remain isolated by source: five videos are train-only and the
    # designated holdout video's frames are test-only. Only reviewed labels enter.
    challenge_manifest = CHALLENGE / "annotation_manifest.json"
    if challenge_manifest.exists():
        for item in json.loads(challenge_manifest.read_text(encoding="utf-8"))["images"]:
            source_label = ROOT / item["label_path"]
            if not source_label.exists() or not source_label.read_text(encoding="utf-8").strip():
                continue
            split = item["split"]
            stem = f"challenge__{item['id']}"
            target_image = DATASET / "images" / split / f"{stem}.jpg"
            target_label = DATASET / "labels" / split / f"{stem}.txt"
            _copy_image(ROOT / item["image_path"], target_image)
            target_label.write_text(
                "\n".join(_read_yolo(source_label, EXPANDED_CLASS_MAP)) + "\n", encoding="utf-8"
            )
            records.append({
                "id": stem,
                "split": split,
                "source": "challenge_video",
                "source_image": item["image_path"],
                "source_label": item["label_path"],
                "source_video": item["source_video"],
                "timestamp": item["timestamp"],
                "phase": item["phase"],
                "label_source": "manual_annotation",
            })

    dataset_yaml = (
        f"path: {DATASET.as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n\n"
        "test: images/test\n\n"
        "names:\n"
        + "".join(f"  {index}: {name}\n" for index, name in enumerate(CLASSES))
    )
    (DATASET / "dataset.yaml").write_text(dataset_yaml, encoding="utf-8")
    payload = {"classes": CLASSES, "records": records}
    (DATASET / "manifest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    counts = {split: sum(record["split"] == split for record in records) for split in ("train", "val", "test")}
    return {
        "dataset": str(DATASET),
        "classes": CLASSES,
        "images": len(records),
        "splits": counts,
        "manual_expanded_images": sum(
            record["source"] == "expanded_dataset" and record["label_source"] == "manual_annotation"
            for record in records
        ),
        "legacy_reviewed_images": sum(record["source"] == "legacy_reviewed" for record in records),
        "auto_worker_images": sum(record["label_source"] == "auto_worker_assist" for record in records),
    }


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
