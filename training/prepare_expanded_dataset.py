from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT.parent / "Data"
DATASET = ROOT / "datasets" / "expanded_construction"
CLASSES = [
    "blowing_machine",
    "cable_reel",
    "air_compressor",
    "fiber_cable",
    "worker",
    "fusion_splicer",
    "fiber",
    "splice_tray",
    "splice_closure",
    "manhole",
]

SOURCES = [
    {
        "key": "air",
        "root": SOURCE_ROOT / "Air_Blowing_visual_dataset_300",
        "metadata": "metadata_selected.csv",
        "image_dir": Path("images") / "selected",
        "suggested_field": "suggested_present_classes",
    },
    {
        "key": "fusion",
        "root": SOURCE_ROOT / "fusion_splicer",
        "metadata": "metadata_selected.csv",
        "image_dir": Path("images") / "selected",
        "suggested_field": "suggested_present_classes",
    },
    {
        "key": "joint",
        "root": SOURCE_ROOT / "joint_closure_dataset",
        "metadata": "metadata_selected.csv",
        "image_dir": Path("images") / "selected",
        "suggested_field": "suggested_classes",
    },
]


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in value)


def _split(index: int, total: int) -> str:
    # Keep later frames as validation/test windows instead of mixing adjacent frames.
    train_end = max(1, round(total * 0.70))
    val_end = max(train_end + 1, round(total * 0.85))
    if index < train_end:
        return "train"
    if index < val_end:
        return "val"
    return "test"


def prepare_dataset(reset: bool = False) -> dict:
    if reset and DATASET.exists():
        shutil.rmtree(DATASET)
    for split in ("train", "val", "test"):
        (DATASET / "images" / split).mkdir(parents=True, exist_ok=True)
        (DATASET / "labels" / split).mkdir(parents=True, exist_ok=True)

    manifest: list[dict] = []
    for source in SOURCES:
        root = source["root"]
        metadata_path = root / source["metadata"]
        if not metadata_path.exists():
            raise FileNotFoundError(f"缺少数据集元数据：{metadata_path}")
        with metadata_path.open("r", encoding="utf-8-sig", newline="") as stream:
            metadata = {row["filename"]: row for row in csv.DictReader(stream)}
        image_paths = sorted((root / source["image_dir"]).glob("*.*"))
        groups: dict[str, list[Path]] = {}
        for path in image_paths:
            row = metadata.get(path.name, {})
            groups.setdefault(row.get("source_video", "unknown"), []).append(path)
        for group_paths in groups.values():
            for index, source_path in enumerate(group_paths):
                row = metadata.get(source_path.name, {})
                split = _split(index, len(group_paths))
                stem = f"{source['key']}__{_safe_name(source_path.stem)}"
                target = DATASET / "images" / split / f"{stem}{source_path.suffix.lower()}"
                if not target.exists() or target.stat().st_size != source_path.stat().st_size:
                    shutil.copy2(source_path, target)
                suggested = row.get(source["suggested_field"], "")
                manifest.append(
                    {
                        "id": stem,
                        "filename": target.name,
                        "split": split,
                        "source_dataset": source["key"],
                        "source_file": str(source_path),
                        "source_video": row.get("source_video", ""),
                        "timestamp": row.get("timestamp", ""),
                        "phase": row.get("phase", ""),
                        "suggested_classes": [item for item in suggested.split(";") if item],
                        "image_path": target.relative_to(ROOT).as_posix(),
                        "label_path": (DATASET / "labels" / split / f"{stem}.txt").relative_to(ROOT).as_posix(),
                    }
                )

    manifest.sort(key=lambda item: item["id"])
    (DATASET / "annotation_manifest.json").write_text(
        json.dumps({"classes": CLASSES, "images": manifest}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    dataset_yaml = "path: " + str(DATASET).replace("\\", "/") + "\n"
    dataset_yaml += "train: images/train\nval: images/val\ntest: images/test\n\nnames:\n"
    dataset_yaml += "".join(f"  {index}: {name}\n" for index, name in enumerate(CLASSES))
    (DATASET / "dataset.yaml").write_text(dataset_yaml, encoding="utf-8")
    return {
        "dataset": str(DATASET),
        "image_count": len(manifest),
        "splits": {split: sum(item["split"] == split for item in manifest) for split in ("train", "val", "test")},
        "classes": CLASSES,
        "annotated_count": sum((DATASET / item["label_path"]).exists() for item in manifest),
    }


if __name__ == "__main__":
    print(json.dumps(prepare_dataset(), ensure_ascii=False, indent=2))
