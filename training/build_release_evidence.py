from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.database import initialize_database
from backend.app.exports import build_archive, build_excel, build_pdf


RELEASE = ROOT / "release_evidence"
SECTIONS = ("models", "model_metrics", "business_metrics", "test_results", "demo_case",
            "digital_delivery", "screenshots", "data_manifest", "licenses")


def copy(source: Path, section: str, name: str | None = None) -> bool:
    if not source.exists():
        return False
    target = RELEASE / section / (name or source.name)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return True


def build() -> dict:
    for section in SECTIONS:
        (RELEASE / section).mkdir(parents=True, exist_ok=True)
    missing = []
    for weight in (ROOT / "backend" / "models").glob("*.pt"):
        copy(weight, "models")
    for summary in (ROOT / "backend" / "models").glob("*summary*.json"):
        copy(summary, "model_metrics")
    for result in (ROOT / "backend" / "models" / "training_runs").glob("*/results.csv"):
        copy(result, "model_metrics", f"{result.parent.name}_results.csv")
    for plot in (ROOT / "backend" / "models" / "training_runs").glob("*/confusion_matrix*.png"):
        copy(plot, "model_metrics", f"{plot.parent.name}_{plot.name}")
    for name in ("safety_business_evaluation.json", "safety_business_confusion_matrix.png", "safety_business_cases.csv"):
        if not copy(ROOT / "evaluation_results" / name, "business_metrics"):
            missing.append(f"business_metrics/{name}")

    tests = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, capture_output=True, text=True)
    (RELEASE / "test_results" / "pytest.txt").write_text(
        tests.stdout + tests.stderr + f"\nEXIT_CODE={tests.returncode}\n", encoding="utf-8"
    )
    check = subprocess.run([sys.executable, str(ROOT / "self_check.py")], cwd=ROOT, capture_output=True, text=True)
    (RELEASE / "test_results" / "system_check.txt").write_text(
        check.stdout + check.stderr + f"\nEXIT_CODE={check.returncode}\n", encoding="utf-8"
    )

    for source in (ROOT / "cross_scene_validation_report.md", ROOT / "demo_air_blowing" / "video_profiles.json",
                   ROOT / "demo_air_blowing" / "fiber_splicing_profile.json"):
        copy(source, "demo_case")
    for frame in sorted((ROOT / "demo_air_blowing" / "frames").glob("*/*.png"))[:12]:
        copy(frame, "demo_case", f"{frame.parent.name}_{frame.name}")

    initialize_database()
    (RELEASE / "digital_delivery" / "验真报告.pdf").write_bytes(build_pdf())
    (RELEASE / "digital_delivery" / "验真数据.xlsx").write_bytes(build_excel())
    (RELEASE / "digital_delivery" / "数字交付档案.zip").write_bytes(build_archive())

    manifests = (
        ROOT / "datasets" / "challenge_video_construction" / "annotation_manifest.json",
        ROOT / "datasets" / "challenge_video_construction" / "frozen_split_manifest.json",
        ROOT / "datasets" / "video_construction_combined" / "manifest.json",
        ROOT / "datasets" / "challenge_video_construction" / "safety_business_ground_truth.csv",
    )
    for source in manifests:
        if not copy(source, "data_manifest"):
            missing.append(f"data_manifest/{source.name}")
    copy(ROOT.parents[1] / "construction-ppe" / "LICENSE", "licenses", "construction-ppe_LICENSE.txt")
    (RELEASE / "licenses" / "THIRD_PARTY_SOURCES.md").write_text(
        "# 第三方来源\n\n- construction-ppe：Ultralytics公开数据，AGPL-3.0。\n"
        "- 安全基线配置参考：https://github.com/vamsiprasanth/constructionsafety 。未复制其源码，仓库未提供明确LICENSE文件。\n"
        "- 新增施工视频：参赛提交前需由项目负责人确认使用授权。\n", encoding="utf-8"
    )
    if not any((RELEASE / "screenshots").iterdir()):
        missing.append("screenshots/页面截图")

    files = []
    for path in sorted(RELEASE.rglob("*")):
        if path.is_file() and path.name not in {"release_manifest.json", "missing_items.json"}:
            files.append({"path": path.relative_to(RELEASE).as_posix(), "size": path.stat().st_size,
                          "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    payload = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": "complete" if not missing and tests.returncode == 0 and check.returncode == 0 else "incomplete",
        "tests_exit_code": tests.returncode, "system_check_exit_code": check.returncode,
        "missing_items": missing, "files": files,
    }
    (RELEASE / "data_manifest" / "missing_items.json").write_text(json.dumps(missing, ensure_ascii=False, indent=2), encoding="utf-8")
    (RELEASE / "data_manifest" / "release_manifest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    archive = ROOT / "release_evidence.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
        for path in RELEASE.rglob("*"):
            if path.is_file(): output.write(path, path.relative_to(ROOT))
    return {**payload, "archive": str(archive)}


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
