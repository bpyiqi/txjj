from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

from backend.app.database import db, initialize_database
from backend.app.engine import synchronize_all
from backend.app.exports import build_archive, build_excel, build_pdf
from backend.app.gis_importer import import_geojson


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"[PASS] {label}")


def main() -> int:
    print("=" * 62)
    print("  通信基建施工透明化管理系统 - 系统自检")
    print("=" * 62)
    try:
        # Create/migrate missing structures only; never reset user uploads or analyses.
        initialize_database()
        imported = import_geojson()
        if imported["changed"]:
            synchronize_all()
        with db() as conn:
            object_count = conn.execute("SELECT COUNT(*) n FROM objects").fetchone()["n"]
            evidence_count = conn.execute("SELECT COUNT(*) n FROM evidence").fetchone()["n"]
            rule_count = conn.execute("SELECT COUNT(*) n FROM rules").fetchone()["n"]
            mandatory_count = conn.execute("SELECT COUNT(*) n FROM rules WHERE mandatory=1").fetchone()["n"]
            issue_count = conn.execute("SELECT COUNT(*) n FROM issues WHERE status!='已关闭'").fetchone()["n"]
            gis_layers = {r["layer"] for r in conn.execute("SELECT DISTINCT layer FROM gis_features")}
            status_total = conn.execute("SELECT COUNT(*) n FROM verification_results").fetchone()["n"]
        check(object_count >= 30, f"工程对象已加载（当前{object_count}个）")
        check(evidence_count >= 57, f"影像证据可用（当前{evidence_count}条）")
        check(rule_count == 15 and mandatory_count == 5, "15条规则及5条强制规则已加载")
        check(status_total == object_count, "全部对象已生成验真结果")
        check({"CABLE", "PTECH", "SITE", "INFRASTRUCTURE"}.issubset(gis_layers), "GIS点线图层完整")
        check(issue_count >= 0, f"问题数据可读取（当前{issue_count}条待处置）")

        demo_video = Path('demo_upload/PBO-JAD-MAR-0008_site_inspection.mp4')
        check(demo_video.exists() and demo_video.stat().st_size > 100_000, "MP4视频抽帧演示素材可用")
        import cv2
        cap = cv2.VideoCapture(str(demo_video))
        video_ok = cap.isOpened() and cap.get(cv2.CAP_PROP_FRAME_COUNT) > 0 and cap.get(cv2.CAP_PROP_FPS) > 0
        cap.release()
        check(video_ok, "OpenCV视频解码组件可用")

        excel = build_excel()
        pdf = build_pdf()
        archive = build_archive()
        check(len(excel) > 10_000 and excel[:2] == b"PK", "Excel验真数据可生成")
        check(len(pdf) > 5_000 and pdf.startswith(b"%PDF"), "PDF验真报告可生成")
        with zipfile.ZipFile(io.BytesIO(archive)) as zf:
            names = set(zf.namelist())
            manifest = json.loads(zf.read("manifest.json"))
        check("reports/验真报告.pdf" in names and "reports/验真数据.xlsx" in names, "ZIP交付档案结构完整")
        check(manifest["object_count"] == object_count and manifest["evidence_count"] == evidence_count, "ZIP manifest数据一致")

        print("-" * 62)
        return 0
    except Exception as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
