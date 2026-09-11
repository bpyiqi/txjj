from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "datasets" / "challenge_video_construction"
MANIFEST = DATASET / "annotation_manifest.json"
LOCK = DATASET / "frozen_split_manifest.json"
GROUND_TRUTH = DATASET / "safety_business_ground_truth.csv"
EVENTS = ("no_helmet", "no_vest", "restricted_area", "vehicle_person_risk")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_label_line(line: str, path: Path, number: int, class_count: int) -> int:
    parts = line.split()
    try:
        class_id = int(parts[0])
        cx, cy, width, height = map(float, parts[1:])
    except (IndexError, ValueError) as exc:
        raise ValueError(f"无效真值：{path}:{number}") from exc
    if len(parts) != 5 or class_id not in range(class_count):
        raise ValueError(f"无效真值：{path}:{number}")
    if not (0 <= cx <= 1 and 0 <= cy <= 1 and 0 < width <= 1 and 0 < height <= 1):
        raise ValueError(f"无效真值：{path}:{number}")
    if cx - width / 2 < 0 or cy - height / 2 < 0 or cx + width / 2 > 1 or cy + height / 2 > 1:
        raise ValueError(f"标注框超出图片：{path}:{number}")
    return class_id


def load_business_truth(test_ids: set[str]) -> tuple[dict[str, dict], dict[str, int]]:
    if not GROUND_TRUTH.exists():
        raise ValueError("缺少116张安全业务人工真值")
    with GROUND_TRUTH.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    keyed = {row.get("case_id", ""): row for row in rows}
    if len(keyed) != len(rows) or set(keyed) != test_ids:
        raise ValueError(f"安全业务真值样本不匹配：应为 {len(test_ids)} 张，当前为 {len(keyed)} 张")
    incomplete = [
        case_id for case_id, row in keyed.items()
        if any(row.get(event) not in {"0", "1"} for event in EVENTS)
        or not row.get("reviewer", "").strip() or not row.get("reviewed_at", "").strip()
    ]
    if incomplete:
        raise ValueError(f"尚有 {len(incomplete)} 张安全业务真值未完成人工复核；数据集未冻结")
    return keyed, {event: sum(row[event] == "1" for row in rows) for event in EVENTS}


def freeze() -> dict:
    source = json.loads(MANIFEST.read_text(encoding="utf-8"))
    pending = []
    records = []
    class_counts = {name: 0 for name in source["classes"]}
    train_items = [item for item in source["images"] if item["split"] == "train"]
    test_items = [item for item in source["images"] if item["split"] == "test"]
    for item in train_items:
        label = ROOT / item["label_path"]
        review = DATASET / "reviews" / item["split"] / f"{item['id']}.json"
        if not label.exists() or not review.exists():
            pending.append(item["id"])
            continue
        for number, line in enumerate(label.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                class_id = validate_label_line(line, label, number, len(source["classes"]))
                class_counts[source["classes"][class_id]] += 1
        records.append({
            "id": item["id"], "split": item["split"], "source_video_sha256": item["source_video_sha256"],
            "image_sha256": digest(ROOT / item["image_path"]), "label_sha256": digest(label),
            "review_sha256": digest(review), "truth_type": "construction_boxes",
        })
    if pending:
        raise ValueError(f"尚有 {len(pending)} 张施工训练帧未完成人工复核；数据集未冻结")
    business_truth, event_counts = load_business_truth({item["id"] for item in test_items})
    for item in test_items:
        row = business_truth[item["id"]]
        records.append({
            "id": item["id"], "split": item["split"], "source_video_sha256": item["source_video_sha256"],
            "image_sha256": digest(ROOT / item["image_path"]), "truth_type": "safety_business_events",
            "truth_sha256": hashlib.sha256(json.dumps(row, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
        })
    payload = {
        "status": "frozen", "frozen_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "classes": source["classes"], "holdout_video": source["holdout_video"],
        "split_policy": source["split_policy"],
        "counts": {split: sum(x["split"] == split for x in records) for split in ("train", "val", "test")},
        "class_box_counts": class_counts, "business_event_positive_counts": event_counts,
        "annotation_manifest_sha256": digest(MANIFEST), "business_ground_truth_sha256": digest(GROUND_TRUTH),
        "records": records,
    }
    LOCK.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(freeze(), ensure_ascii=False, indent=2))
