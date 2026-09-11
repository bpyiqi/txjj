from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.yolo_safety import MODEL_PATH, detect_at_timestamps


DATASET = ROOT / "datasets" / "challenge_video_construction"
OUTPUT = ROOT / "evaluation_results"
TRUTH = DATASET / "safety_business_ground_truth.csv"
EVENTS = ("no_helmet", "no_vest", "restricted_area", "vehicle_person_risk")


def prepare_truth() -> int:
    manifest = json.loads((DATASET / "annotation_manifest.json").read_text(encoding="utf-8"))
    rows = [item for item in manifest["images"] if item["split"] == "test"]
    if not TRUTH.exists():
        with TRUTH.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["case_id", "timestamp", *EVENTS, "reviewer", "reviewed_at"])
            writer.writeheader()
            for item in rows:
                writer.writerow({"case_id": item["id"], "timestamp": item["timestamp"]})
    return len(rows)


def metrics(tp: int, fp: int, fn: int, tn: int) -> dict:
    total = tp + fp + fn + tn
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "accuracy": (tp + tn) / total if total else 0.0,
        "precision": precision, "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
    }


def evaluate() -> dict:
    test_images = prepare_truth()
    truth_rows = list(csv.DictReader(TRUTH.open("r", encoding="utf-8-sig", newline="")))
    missing = [row["case_id"] for row in truth_rows if row["no_helmet"].strip() not in {"0", "1"}]
    if missing:
        raise ValueError(f"请先在 {TRUTH} 完成116张测试图的 no_helmet 人工真值；当前缺少 {len(missing)} 张")
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"安全模型尚未生成：{MODEL_PATH}")
    manifest = json.loads((DATASET / "annotation_manifest.json").read_text(encoding="utf-8"))
    holdout = next(item for item in manifest["videos"] if item["role"] == "independent_test")
    timestamps = [float(row["timestamp"]) for row in truth_rows]
    inference = detect_at_timestamps(Path(holdout["source_path"]), timestamps)
    cases = []
    tp = fp = fn = tn = 0
    for truth, frame in zip(truth_rows, inference["frames"]):
        predicted = int(any(risk.get("risk") == "safety_helmet_missing" for risk in frame["risks"]))
        actual = int(truth["no_helmet"])
        outcome = "TP" if actual and predicted else "FP" if predicted else "FN" if actual else "TN"
        tp += outcome == "TP"; fp += outcome == "FP"; fn += outcome == "FN"; tn += outcome == "TN"
        confidence = max((float(x.get("confidence", 0)) for x in frame["risks"]), default=0.0)
        cases.append({"case_id": truth["case_id"], "timestamp": truth["timestamp"], "event": "no_helmet",
                      "actual": actual, "predicted": predicted, "outcome": outcome, "confidence": confidence})
    result = metrics(tp, fp, fn, tn)
    event_result = {"no_helmet": {"status": "evaluated", **result}}
    for event in EVENTS[1:]:
        event_result[event] = {"status": "not_supported", "reason": "当前平台没有该事件的已验证模型或规则"}
    report = {
        "evaluated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": "completed", "test_images": test_images,
        **{key: result[key] for key in ("accuracy", "precision", "recall", "f1")},
        "events": event_result, "model_weights": str(MODEL_PATH), "holdout_video_sha256": holdout["sha256"],
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "safety_business_evaluation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with (OUTPUT / "safety_business_cases.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(cases[0])); writer.writeheader(); writer.writerows(cases)
    canvas = np.full((560, 720, 3), 255, np.uint8)
    cv2.putText(canvas, "Safety Business Confusion Matrix", (80, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (20, 45, 65), 2)
    for row, (left, right) in enumerate(((tn, fp), (fn, tp))):
        for col, value in enumerate((left, right)):
            x, y = 150 + col * 250, 120 + row * 190
            cv2.rectangle(canvas, (x, y), (x + 220, y + 160), (225, 242, 250) if row == col else (235, 235, 235), -1)
            cv2.putText(canvas, str(value), (x + 85, y + 95), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (20, 45, 65), 3)
    cv2.putText(canvas, "Predicted: 0", (165, 500), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 45, 65), 1)
    cv2.putText(canvas, "Predicted: 1", (415, 500), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 45, 65), 1)
    ok, png = cv2.imencode(".png", canvas)
    if not ok: raise OSError("混淆矩阵生成失败")
    (OUTPUT / "safety_business_confusion_matrix.png").write_bytes(png.tobytes())
    return report


if __name__ == "__main__":
    print(json.dumps(evaluate(), ensure_ascii=False, indent=2))
