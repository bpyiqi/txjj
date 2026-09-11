from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2


ROOT = Path(__file__).resolve().parents[1]


def read_labels(path: Path) -> list[tuple[int, float, float, float, float]]:
    records = []
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        records.append((int(parts[0]), *(float(value) for value in parts[1:5])))
    return records


def render(limit: int, output: Path, label_root: Path | None = None) -> dict:
    dataset = ROOT / "datasets" / "expanded_construction"
    manifest = json.loads((dataset / "annotation_manifest.json").read_text(encoding="utf-8"))
    classes = manifest["classes"]
    items = []
    for item in manifest["images"]:
        label_path = (label_root / item["split"] / f"{item['id']}.txt") if label_root else ROOT / item["label_path"]
        if label_path.exists() and read_labels(label_path):
            items.append((item, label_path))
    items = items[:limit]
    if not items:
        raise SystemExit("No non-empty labels found")

    tiles = []
    for item, label_path in items:
        image = cv2.imread(str(ROOT / item["image_path"]))
        if image is None:
            continue
        height, width = image.shape[:2]
        for class_id, x, y, box_width, box_height in read_labels(label_path):
            left = max(0, int((x - box_width / 2) * width))
            top = max(0, int((y - box_height / 2) * height))
            right = min(width - 1, int((x + box_width / 2) * width))
            bottom = min(height - 1, int((y + box_height / 2) * height))
            color = ((37 * class_id) % 220 + 25, (91 * class_id) % 220 + 25, (157 * class_id) % 220 + 25)
            cv2.rectangle(image, (left, top), (right, bottom), color, 3)
            label = f"{class_id}:{classes[class_id]}"
            cv2.putText(image, label, (left, max(20, top - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)
        title = f"{item['id']} | {item.get('phase', '')}"
        cv2.rectangle(image, (0, 0), (width, 34), (20, 35, 50), -1)
        cv2.putText(image, title[:110], (8, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 2)
        scale = min(1.0, 640 / width)
        image = cv2.resize(image, (int(width * scale), int(height * scale)))
        tiles.append(image)

    tile_width = max(tile.shape[1] for tile in tiles)
    tile_height = max(tile.shape[0] for tile in tiles)
    columns = 3
    rows = (len(tiles) + columns - 1) // columns
    sheet = 255 * __import__("numpy").ones((rows * tile_height, columns * tile_width, 3), dtype="uint8")
    for index, tile in enumerate(tiles):
        row, column = divmod(index, columns)
        sheet[row * tile_height : row * tile_height + tile.shape[0], column * tile_width : column * tile_width + tile.shape[1]] = tile
    output.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output), sheet)
    return {"labeled_images": len(tiles), "output": str(output)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=29)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs" / "manual_label_review.jpg")
    parser.add_argument("--label-root", type=Path, default=None)
    args = parser.parse_args()
    print(json.dumps(render(args.limit, args.output, args.label_root), ensure_ascii=False, indent=2))
