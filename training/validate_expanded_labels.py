from __future__ import annotations

import json
from pathlib import Path

from prepare_expanded_dataset import CLASSES, DATASET, ROOT, prepare_dataset


def validate() -> dict:
    prepare_dataset()
    manifest = json.loads((DATASET / "annotation_manifest.json").read_text(encoding="utf-8"))
    errors: list[str] = []
    boxes = 0
    class_counts = {name: 0 for name in CLASSES}
    annotated = 0
    for item in manifest["images"]:
        label_path = ROOT / item["label_path"]
        if not label_path.exists():
            continue
        lines = [line for line in label_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if lines:
            annotated += 1
        for line_no, line in enumerate(lines, start=1):
            parts = line.split()
            if len(parts) != 5:
                errors.append(f"{label_path}:{line_no}: 应为5列")
                continue
            try:
                class_id, cx, cy, width, height = map(float, parts)
            except ValueError:
                errors.append(f"{label_path}:{line_no}: 存在非数字字段")
                continue
            if int(class_id) != class_id or not 0 <= int(class_id) < len(CLASSES):
                errors.append(f"{label_path}:{line_no}: 类别编号无效")
                continue
            if any(value < 0 or value > 1 for value in (cx, cy, width, height)) or width <= 0 or height <= 0:
                errors.append(f"{label_path}:{line_no}: 坐标未归一化或尺寸无效")
                continue
            if cx - width / 2 < 0 or cy - height / 2 < 0 or cx + width / 2 > 1 or cy + height / 2 > 1:
                errors.append(f"{label_path}:{line_no}: 标注框超出图片")
                continue
            boxes += 1
            class_counts[CLASSES[int(class_id)]] += 1
    return {"annotated_images": annotated, "box_count": boxes, "class_counts": class_counts, "errors": errors}


if __name__ == "__main__":
    print(json.dumps(validate(), ensure_ascii=False, indent=2))
