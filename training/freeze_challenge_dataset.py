from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "datasets" / "challenge_video_construction"
MANIFEST = DATASET / "annotation_manifest.json"
LOCK = DATASET / "frozen_split_manifest.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze() -> dict:
    source = json.loads(MANIFEST.read_text(encoding="utf-8"))
    pending = []
    records = []
    for item in source["images"]:
        label = ROOT / item["label_path"]
        review = DATASET / "reviews" / item["split"] / f"{item['id']}.json"
        if not label.exists() or not review.exists():
            pending.append(item["id"])
            continue
        for number, line in enumerate(label.read_text(encoding="utf-8").splitlines(), 1):
            parts = line.split()
            if len(parts) != 5 or int(parts[0]) not in range(3) or not all(0 <= float(v) <= 1 for v in parts[1:]):
                raise ValueError(f"无效真值：{label}:{number}")
        records.append({
            "id": item["id"], "split": item["split"], "source_video_sha256": item["source_video_sha256"],
            "image_sha256": digest(ROOT / item["image_path"]), "label_sha256": digest(label),
            "review_sha256": digest(review),
        })
    if pending:
        raise ValueError(f"尚有 {len(pending)} 张未完成人工复核；数据集未冻结")
    payload = {
        "status": "frozen", "frozen_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "classes": source["classes"], "holdout_video": source["holdout_video"],
        "split_policy": source["split_policy"],
        "counts": {split: sum(x["split"] == split for x in records) for split in ("train", "val", "test")},
        "annotation_manifest_sha256": digest(MANIFEST), "records": records,
    }
    LOCK.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(freeze(), ensure_ascii=False, indent=2))
