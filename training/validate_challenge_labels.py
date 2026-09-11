from __future__ import annotations

import json
from pathlib import Path

from freeze_challenge_dataset import DATASET, MANIFEST, ROOT, validate_label_line


def validate() -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    classes = manifest["classes"]
    items = [item for item in manifest["images"] if item["split"] == "train"]
    class_counts = {name: 0 for name in classes}
    reviewed = empty = boxes = 0
    errors: list[str] = []
    for item in items:
        label = ROOT / item["label_path"]
        review = DATASET / "reviews" / "train" / f"{item['id']}.json"
        if not label.exists() or not review.exists():
            continue
        reviewed += 1
        lines = [line for line in label.read_text(encoding="utf-8").splitlines() if line.strip()]
        empty += not lines
        for number, line in enumerate(lines, 1):
            try:
                class_id = validate_label_line(line, label, number, len(classes))
            except ValueError as exc:
                errors.append(str(exc))
                continue
            boxes += 1
            class_counts[classes[class_id]] += 1
    return {
        "total_images": len(items), "reviewed_images": reviewed,
        "pending_images": len(items) - reviewed, "reviewed_empty_images": empty,
        "box_count": boxes, "class_counts": class_counts, "errors": errors,
    }


if __name__ == "__main__":
    result = validate()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(bool(result["pending_images"] or result["errors"]))
