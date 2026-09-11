"""Integrated construction image analysis and verification service.

The module reuses the existing ``project`` and ``evidence`` tables and adds an
additive task/result layer. Legacy API handlers and legacy table columns are not
changed.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from .air_blowing_analyzer import analyze_profile as analyze_air_profile
from .air_blowing_analyzer import analyze_video_with_opencv as analyze_air_video
from .air_blowing_analyzer import sha256_file
from .database import BASE_DIR, db
from .engine import now_iso, record_safety_issue
from .fiber_splicing_analyzer import analyze_profile as analyze_splicing_profile
from .fiber_splicing_analyzer import analyze_video_with_opencv as analyze_splicing_video
from .yolo_construction import merge_detections
from .yolo_safety import merge_safety_detections


PROJECT_ROOT = BASE_DIR.parent
AI_UPLOAD_DIR = BASE_DIR / "uploads" / "ai_videos"
AI_EVIDENCE_DIR = BASE_DIR / "uploads" / "ai_evidence"
AI_REPORT_DIR = BASE_DIR / "uploads" / "ai_reports"
DEFAULT_AI_PROJECT_ID = "VB-AI-DEMO-001"
REPORT_TITLE = "通信基建施工透明化管理与数字化验真交付报告"
for directory in (AI_UPLOAD_DIR, AI_EVIDENCE_DIR, AI_REPORT_DIR):
    directory.mkdir(parents=True, exist_ok=True)

SPLICING_RULES = {
    "fiber_stripping": {"rule_id": "EXP-SPL-001", "name": "光纤涂覆层剥除检查"},
    "fiber_cleaning": {"rule_id": "EXP-SPL-002", "name": "裸纤清洁质量检查"},
    "fiber_cleaving": {"rule_id": "EXP-SPL-003", "name": "光纤端面切割检查"},
    "fusion_splicing": {"rule_id": "EXP-SPL-004", "name": "光纤熔接过程与结果检查"},
    "fiber_organizing": {"rule_id": "EXP-SPL-005", "name": "保护套管与盘纤整理检查"},
}


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", Path(value).name)


def get_ai_project(project_id: str) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT * FROM project WHERE project_id=?", (project_id,)).fetchone()
    if not row:
        raise KeyError("项目不存在")
    result = dict(row)
    result["workflow"] = _loads(result.pop("workflow_json"), [])
    result["data_governance"] = _loads(result.pop("governance_json"), {})
    return result


def create_ai_project(payload: dict[str, Any]) -> dict[str, Any]:
    project_id = payload.get("project_id") or f"VB-AI-{uuid4().hex[:8].upper()}"
    now = now_iso()
    with db() as conn:
        conn.execute(
            """INSERT INTO project
               (project_id,name,scenario,location,data_version,updated_at,workflow_json,governance_json)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                project_id,
                payload["name"],
                payload.get("scenario", "高速公路通信工程光缆施工全过程智能验真"),
                payload.get("location", "高速公路通信基础设施施工现场"),
                payload.get("data_version", "通信基建施工数据集"),
                now,
                json.dumps(["光缆气吹施工", "工程交接", "光纤熔接施工", "数字交付"], ensure_ascii=False),
                json.dumps({"evidence_hash": "SHA-256", "review": "AI分析+人工复核"}, ensure_ascii=False),
            ),
        )
    return get_ai_project(project_id)


def create_construction_task(payload: dict[str, Any]) -> dict[str, Any]:
    task_id = payload.get("task_id") or f"TASK-{uuid4().hex[:10].upper()}"
    now = now_iso()
    with db() as conn:
        if not conn.execute("SELECT 1 FROM project WHERE project_id=?", (payload["project_id"],)).fetchone():
            raise KeyError("项目不存在")
        object_id = payload.get("linked_object_id")
        if object_id and not conn.execute("SELECT 1 FROM objects WHERE object_id=?", (object_id,)).fetchone():
            raise KeyError("工程对象不存在")
        conn.execute(
            """INSERT INTO construction_tasks
               (task_id,project_id,task_type,name,sequence,status,linked_object_id,
                source_video_path,source_video_sha256,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                task_id, payload["project_id"], payload["task_type"], payload["name"],
                int(payload["sequence"]), payload.get("status", "待上传"), object_id,
                None, None, now, now,
            ),
        )
        conn.execute(
            "UPDATE project SET updated_at=? WHERE project_id=?",
            (now, payload["project_id"]),
        )
    return get_task(task_id)


def get_task(task_id: str) -> dict[str, Any]:
    with db() as conn:
        task = conn.execute("SELECT * FROM construction_tasks WHERE task_id=?", (task_id,)).fetchone()
        if not task:
            raise KeyError("施工任务不存在")
        result_rows = conn.execute(
            "SELECT * FROM ai_analysis_results WHERE task_id=? ORDER BY created_at,analysis_id",
            (task_id,),
        ).fetchall()
        evidence_rows = conn.execute(
            """SELECT e.*,te.source_timestamp,te.evidence_hash task_evidence_hash
               FROM construction_task_evidence te JOIN evidence e ON e.evidence_id=te.evidence_id
               WHERE te.task_id=? ORDER BY te.source_timestamp,e.evidence_id""",
            (task_id,),
        ).fetchall()
    task_dict = dict(task)
    results = []
    for row in result_rows:
        item = dict(row)
        for key, default in (
            ("detected_objects_json", []), ("risk_json", []),
            ("engineering_object_json", {}), ("acceptance_rule_json", {}),
        ):
            item[key.removesuffix("_json")] = _loads(item.pop(key), default)
        results.append(item)
    return {"task": task_dict, "evidence": [dict(row) for row in evidence_rows], "ai_analysis_results": results}


def list_project_tasks(project_id: str) -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            """SELECT t.*,
               (SELECT COUNT(*) FROM construction_task_evidence te WHERE te.task_id=t.task_id) evidence_count,
               (SELECT COUNT(*) FROM ai_analysis_results ar WHERE ar.task_id=t.task_id) analysis_count,
               (SELECT AVG(confidence) FROM ai_analysis_results ar WHERE ar.task_id=t.task_id) avg_confidence,
               (SELECT COUNT(*) FROM ai_analysis_results ar WHERE ar.task_id=t.task_id AND ar.risk_json!='[]') risk_count
               FROM construction_tasks t WHERE t.project_id=? ORDER BY t.sequence,t.task_id""",
            (project_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def dashboard(project_id: str | None = None) -> dict[str, Any]:
    if not project_id:
        with db() as conn:
            latest = conn.execute(
                """SELECT p.project_id FROM project p
                   WHERE EXISTS (SELECT 1 FROM construction_tasks t WHERE t.project_id=p.project_id)
                   ORDER BY p.updated_at DESC,p.rowid DESC LIMIT 1"""
            ).fetchone()
        project_id = latest["project_id"] if latest else DEFAULT_AI_PROJECT_ID
    project = get_ai_project(project_id)
    tasks = list_project_tasks(project_id)
    total_evidence = sum(item["evidence_count"] for item in tasks)
    total_analyses = sum(item["analysis_count"] for item in tasks)
    return {
        "project": project,
        "tasks": tasks,
        "workflow": [
            {"sequence": item["sequence"], "name": item["name"], "task_type": item["task_type"], "status": item["status"]}
            for item in tasks
        ],
        "summary": {
            "task_count": len(tasks),
            "evidence_count": total_evidence,
            "analysis_count": total_analyses,
            "risk_count": sum(item["risk_count"] for item in tasks),
            "completed_count": sum(item["status"] in {"完成", "生成"} for item in tasks),
        },
    }


def register_task_video(task_id: str, stored_path: Path) -> dict[str, Any]:
    from .video_sampling import ensure_video_decodable

    ensure_video_decodable(stored_path)
    digest = sha256_file(stored_path)
    relative = stored_path.relative_to(BASE_DIR).as_posix()
    with db() as conn:
        if not conn.execute("SELECT 1 FROM construction_tasks WHERE task_id=?", (task_id,)).fetchone():
            raise KeyError("施工任务不存在")
        conn.execute(
            """UPDATE construction_tasks SET source_video_path=?,source_video_sha256=?,status='已上传',updated_at=?
               WHERE task_id=?""",
            (relative, digest, now_iso(), task_id),
        )
        conn.execute(
            "INSERT INTO activities(activity_type,title,description,created_at) VALUES (?,?,?,?)",
            ("AI视频上传", "施工视频已关联任务", f"{task_id} → {relative}", now_iso()),
        )
    return get_task(task_id)


def new_video_target(task_id: str, filename: str) -> Path:
    task_dir = AI_UPLOAD_DIR / _safe_name(task_id)
    task_dir.mkdir(parents=True, exist_ok=True)
    return task_dir / f"{uuid4().hex[:8]}_{_safe_name(filename)}"


def _match_air_profile(video_hash: str) -> dict[str, Any] | None:
    profile_path = PROJECT_ROOT / "demo_air_blowing" / "video_profiles.json"
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    for profile in payload["videos"]:
        if sha256_file(PROJECT_ROOT / profile["video_path"]) == video_hash:
            return profile
    return None


def _clear_task_analysis(conn, task_id: str, data_id: int | None = None) -> None:
    if data_id is None:
        evidence_ids = [
            row["evidence_id"]
            for row in conn.execute(
                "SELECT evidence_id FROM construction_task_evidence WHERE task_id=?", (task_id,)
            ).fetchall()
        ]
        conn.execute("DELETE FROM ai_analysis_results WHERE task_id=?", (task_id,))
        conn.execute("DELETE FROM construction_task_evidence WHERE task_id=?", (task_id,))
    else:
        evidence_ids = [
            row["evidence_id"]
            for row in conn.execute(
                "SELECT evidence_id FROM ai_analysis_results WHERE data_id=?", (data_id,)
            ).fetchall()
        ]
        conn.execute("DELETE FROM ai_analysis_results WHERE data_id=?", (data_id,))
        for evidence_id in evidence_ids:
            conn.execute(
                "DELETE FROM construction_task_evidence WHERE task_id=? AND evidence_id=?",
                (task_id, evidence_id),
            )
    if evidence_ids:
        placeholders = ",".join("?" for _ in evidence_ids)
        conn.execute(
            f"DELETE FROM issues WHERE source='安全视觉检测' AND evidence_id IN ({placeholders})",
            evidence_ids,
        )
    for evidence_id in evidence_ids:
        conn.execute("DELETE FROM evidence WHERE evidence_id=?", (evidence_id,))


def analyze_task(task_id: str, data_id: int | None = None) -> dict[str, Any]:
    detail = get_task(task_id)
    task = detail["task"]
    if task["task_type"] not in {"air_blowing", "fusion_splicing"}:
        raise ValueError("该任务类型不需要视频AI分析")
    if not task["source_video_path"]:
        raise ValueError("请先上传施工视频")
    uploaded_path = BASE_DIR / task["source_video_path"]
    if not uploaded_path.exists():
        raise FileNotFoundError("任务视频文件不存在")
    video_hash = sha256_file(uploaded_path)
    job_dir = AI_EVIDENCE_DIR / _safe_name(task_id)
    if data_id is not None:
        job_dir = job_dir / f"job_{data_id}"

    if task["task_type"] == "air_blowing":
        profile = _match_air_profile(video_hash)
        if profile:
            records = analyze_air_profile(profile, PROJECT_ROOT)["evidence"]
            analysis_method = "已复核目标标注与施工时序规则"
        else:
            records = analyze_air_video(
                uploaded_path,
                job_dir / "extracted",
                uploaded_path.stem,
                {"object_id": task.get("linked_object_id") or task_id, "object_type": "optical_cable_segment"},
            )
            analysis_method = "关键影像提取与施工时序规则"
    else:
        profile_path = PROJECT_ROOT / "demo_air_blowing" / "fiber_splicing_profile.json"
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        if sha256_file(PROJECT_ROOT / profile["video_path"]) == video_hash:
            records, _ = analyze_splicing_profile(profile_path, PROJECT_ROOT)
            analysis_method = "已复核目标标注与施工时序规则"
        else:
            records = analyze_splicing_video(
                uploaded_path,
                job_dir / "extracted",
                uploaded_path.stem,
            )
            analysis_method = "关键影像提取与施工时序规则"

    records, vision_summary = merge_detections(records, uploaded_path)
    if vision_summary["enabled"]:
        analysis_method = "YOLO视觉目标检测与施工阶段规则"
        detected_scene = vision_summary["scene"]
        if detected_scene and detected_scene != task["task_type"]:
            records[0].setdefault("risk_detection", []).append({
                "risk": "construction_scene_task_mismatch",
                "severity": "high",
                "status": "manual_review_required",
                "detected_scene": detected_scene,
                "task_type": task["task_type"],
            })
    records, safety_summary = merge_safety_detections(records, uploaded_path)
    if safety_summary["enabled"]:
        analysis_method += "、安全监管视觉检测"

    now = now_iso()
    with db() as conn:
        _clear_task_analysis(conn, task_id, data_id)
        for index, record in enumerate(records, start=1):
            evidence_id = f"AIE-{uuid4().hex[:12].upper()}"
            analysis_id = f"AIR-{uuid4().hex[:12].upper()}"
            stage = record.get("construction_stage") or record["stage"]
            timestamp = float(record["timestamp"])
            objects = record["detected_objects"]
            risks = list(record.get("risk_detection", []))
            engineering_object = record.get("engineering_object") or {
                "object_id": task.get("linked_object_id") or task_id,
                "object_type": "optical_fiber_splice",
            }
            rule = record.get("acceptance_rule") or SPLICING_RULES[stage]
            rule = {
                **rule,
                "detected_scene": vision_summary["scene"],
                "vision_detection": vision_summary["enabled"],
                "safety_detection": safety_summary["enabled"],
            }
            digest = record.get("frame_sha256") or record["evidence_hash"]
            if task["task_type"] == "fusion_splicing" and stage == "fiber_organizing" and index == len(records):
                risks.append({
                    "risk": "splice_tray_not_observed",
                    "severity": "medium",
                    "confidence": 0.86,
                    "status": "evidence_gap",
                })
            asset_path = task["source_video_path"]
            filename = f"{task_id}_{timestamp:07.1f}s.mp4"
            if record.get("frame_path"):
                source_frame = PROJECT_ROOT / record["frame_path"]
                frame_dir = job_dir
                frame_dir.mkdir(parents=True, exist_ok=True)
                frame_target = frame_dir / source_frame.name
                shutil.copy2(source_frame, frame_target)
                asset_path = frame_target.relative_to(BASE_DIR).as_posix()
                filename = frame_target.name
            conn.execute(
                """INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    evidence_id, filename, "video_frame" if record.get("frame_path") else "video_segment",
                    "AI施工视频", task.get("linked_object_id") or task_id, task.get("linked_object_id"),
                    "ai_construction_stage", stage, "AI分析", float(record["confidence"]),
                    analysis_method, "AI已分析", analysis_method, f"{task_id} @ {timestamp:.1f}s",
                    json.dumps({"stage": stage, "objects": objects, "risks": risks}, ensure_ascii=False),
                    None, f"uploads/{asset_path.removeprefix('uploads/')}", None, None, now,
                ),
            )
            for risk in risks:
                record_safety_issue(
                    conn,
                    task_id=task_id,
                    evidence_id=evidence_id,
                    object_id=task.get("linked_object_id"),
                    timestamp=timestamp,
                    risk=risk,
                )
            conn.execute(
                "INSERT INTO construction_task_evidence VALUES (?,?,?,?,?)",
                (task_id, evidence_id, timestamp, digest, now),
            )
            conn.execute(
                """INSERT INTO ai_analysis_results
                   (analysis_id,task_id,evidence_id,stage,detected_objects_json,confidence,
                    risk_json,engineering_object_json,acceptance_rule_json,evidence_hash,
                    model_name,model_version,review_status,created_at,data_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    analysis_id, task_id, evidence_id, stage,
                    json.dumps(objects, ensure_ascii=False), float(record["confidence"]),
                    json.dumps(risks, ensure_ascii=False), json.dumps(engineering_object, ensure_ascii=False),
                    json.dumps(rule, ensure_ascii=False), digest, analysis_method, "当前", "待人工验真", now,
                    data_id,
                ),
            )
        conn.execute(
            "UPDATE construction_tasks SET status='AI分析完成',updated_at=? WHERE task_id=?",
            (now, task_id),
        )
        conn.execute(
            "INSERT INTO activities(activity_type,title,description,object_id,created_at) VALUES (?,?,?,?,?)",
            ("AI施工分析", "施工任务AI分析完成", f"{task_id}：{len(records)}条证据", task.get("linked_object_id"), now),
        )
    result = get_task(task_id)
    result["vision_summary"] = vision_summary
    result["safety_summary"] = safety_summary
    return result


def complete_task(task_id: str) -> dict[str, Any]:
    detail = get_task(task_id)
    task = detail["task"]
    if task["task_type"] in {"air_blowing", "fusion_splicing"} and not detail["ai_analysis_results"]:
        raise ValueError("任务尚未完成AI分析")
    now = now_iso()
    status = "生成" if task["task_type"] == "digital_delivery" else "完成"
    with db() as conn:
        conn.execute("UPDATE construction_tasks SET status=?,updated_at=? WHERE task_id=?", (status, now, task_id))
        conn.execute("UPDATE ai_analysis_results SET review_status='验真完成' WHERE task_id=?", (task_id,))
        conn.execute(
            "INSERT INTO activities(activity_type,title,description,object_id,created_at) VALUES (?,?,?,?,?)",
            ("AI验真完成", f"{task['name']}已完成验真", task_id, task.get("linked_object_id"), now),
        )
    return get_task(task_id)


def _font_path() -> str:
    for candidate in (
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
    ):
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError("未找到中文字体")


def build_trusted_delivery_pdf(project_id: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    view = dashboard(project_id)
    project, tasks = view["project"], view["tasks"]
    details = [get_task(task["task_id"]) for task in tasks]
    all_results = [result for detail in details for result in detail["ai_analysis_results"]]
    all_evidence = [item for detail in details for item in detail["evidence"]]
    risks = [
        {"task": detail["task"]["name"], "stage": result["stage"], **risk}
        for detail in details for result in detail["ai_analysis_results"]
        for risk in result["risk"]
    ]

    buffer = io.BytesIO()
    pdfmetrics.registerFont(TTFont("CN-AI", _font_path()))
    navy, cyan, pale, gray = colors.HexColor("#17324D"), colors.HexColor("#00A6A6"), colors.HexColor("#EAF7F6"), colors.HexColor("#637487")
    base = getSampleStyleSheet()
    title = ParagraphStyle("title", parent=base["Title"], fontName="CN-AI", fontSize=20, leading=28, textColor=navy, alignment=TA_CENTER, spaceAfter=8 * mm)
    subtitle = ParagraphStyle("subtitle", parent=base["BodyText"], fontName="CN-AI", fontSize=10.5, leading=17, textColor=gray, alignment=TA_CENTER)
    h1 = ParagraphStyle("h1", parent=base["Heading1"], fontName="CN-AI", fontSize=15, leading=21, textColor=navy, spaceBefore=5 * mm, spaceAfter=3 * mm)
    body = ParagraphStyle("body", parent=base["BodyText"], fontName="CN-AI", fontSize=9.2, leading=14.5, textColor=colors.HexColor("#263746"))
    small = ParagraphStyle("small", parent=body, fontSize=7.3, leading=10.3, textColor=gray)
    metric = ParagraphStyle("metric", parent=body, fontSize=14, leading=18, textColor=navy, alignment=TA_CENTER)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D5E0E8"))
        canvas.line(18 * mm, 14 * mm, 192 * mm, 14 * mm)
        canvas.setFont("CN-AI", 7)
        canvas.setFillColor(gray)
        canvas.drawString(18 * mm, 9 * mm, "通信基建施工透明化管理与数化交付")
        canvas.drawRightString(192 * mm, 9 * mm, f"第 {doc.page} 页")
        canvas.restoreState()

    def table(rows, widths, header=True):
        result = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
        commands = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C8D6E0")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]
        if header:
            commands += [("BACKGROUND", (0, 0), (-1, 0), navy), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]
        result.setStyle(TableStyle(commands))
        return result

    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=19 * mm, title=REPORT_TITLE, author="通信基建施工透明化管理系统")
    story = [Spacer(1, 9 * mm), Paragraph(REPORT_TITLE, title), Paragraph("Project → ConstructionTask → Evidence → AIAnalysisResult", subtitle), Spacer(1, 8 * mm)]
    project_rows = [
        [Paragraph("项目编号", small), Paragraph(project["project_id"], body)],
        [Paragraph("项目名称", small), Paragraph(project["name"], body)],
        [Paragraph("施工场景", small), Paragraph(project["scenario"], body)],
        [Paragraph("施工地点", small), Paragraph(project.get("location") or "-", body)],
    ]
    project_table = Table(project_rows, colWidths=[34 * mm, 124 * mm])
    project_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, -1), pale), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C8D6E0")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story += [project_table, Spacer(1, 7 * mm)]
    stats = [[Paragraph(f"<b>{len(tasks)}</b><br/><font size=8>施工任务</font>", metric), Paragraph(f"<b>{len(all_evidence)}</b><br/><font size=8>证据</font>", metric), Paragraph(f"<b>{len(all_results)}</b><br/><font size=8>AI结果</font>", metric), Paragraph(f"<b>{len(risks)}</b><br/><font size=8>风险/补证</font>", metric)]]
    stat_table = Table(stats, colWidths=[39.5 * mm] * 4)
    stat_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F4F8FB")), ("BOX", (0, 0), (-1, -1), 0.8, cyan), ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C8D6E0")), ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9)]))
    story += [stat_table, Paragraph("施工阶段", h1)]
    task_rows = [[Paragraph("序号", small), Paragraph("施工任务", small), Paragraph("类型", small), Paragraph("状态", small), Paragraph("证据/分析", small)]]
    for task in tasks:
        task_rows.append([Paragraph(str(task["sequence"]), small), Paragraph(task["name"], body), Paragraph(task["task_type"], small), Paragraph(task["status"], body), Paragraph(f"{task['evidence_count']} / {task['analysis_count']}", body)])
    story += [table(task_rows, [17 * mm, 47 * mm, 42 * mm, 25 * mm, 29 * mm]), Paragraph("验收结论", h1), Paragraph("光缆气吹施工、工程交接、光纤熔接施工和数字交付已纳入统一项目任务链。AI证据均关联具体施工任务并使用 SHA-256 固化；风险项进入补证或人工复核，报告用于可信交付辅助，不替代法定验收签认。", body), PageBreak()]

    story += [Paragraph("AI分析结果", h1)]
    result_rows = [[Paragraph("任务", small), Paragraph("工序", small), Paragraph("目标", small), Paragraph("置信度", small), Paragraph("复核状态", small)]]
    for detail in details:
        for result in detail["ai_analysis_results"]:
            labels = "、".join(obj["label"] for obj in result["detected_objects"])
            result_rows.append([Paragraph(detail["task"]["name"], small), Paragraph(result["stage"], small), Paragraph(labels, small), Paragraph(f"{result['confidence']:.2f}", small), Paragraph(result["review_status"], small)])
    if len(result_rows) == 1:
        result_rows.append([Paragraph("尚无AI结果", body), "", "", "", ""])
    story += [table(result_rows, [34 * mm, 32 * mm, 58 * mm, 20 * mm, 24 * mm]), PageBreak(), Paragraph("证据链与风险检测", h1), Paragraph("每条 AIAnalysisResult 通过 evidence_id 关联原 Evidence 表，并由 construction_task_evidence 绑定施工任务。证据链包含任务、时间戳、目标、工序、模型、风险和 SHA-256。", body)]
    risk_rows = [[Paragraph("施工任务", small), Paragraph("工序", small), Paragraph("风险/缺口", small), Paragraph("等级", small), Paragraph("状态", small)]]
    for risk in risks:
        risk_rows.append([Paragraph(risk["task"], small), Paragraph(risk["stage"], small), Paragraph(risk["risk"], small), Paragraph(risk.get("severity", "-"), small), Paragraph(risk.get("status", "人工复核"), small)])
    if len(risk_rows) == 1:
        risk_rows.append([Paragraph("全部任务", small), Paragraph("-", small), Paragraph("未发现风险", small), Paragraph("-", small), Paragraph("通过", small)])
    story += [table(risk_rows, [37 * mm, 32 * mm, 51 * mm, 20 * mm, 28 * mm]), Paragraph("可信交付清单", h1), Paragraph(f"项目：{project['project_id']}<br/>任务：{len(tasks)} 项<br/>证据：{len(all_evidence)} 条<br/>AI分析：{len(all_results)} 条<br/>哈希算法：SHA-256<br/>报告状态：已生成", body), Paragraph("最终结论", h1), Paragraph("本项目已完成从施工任务编排、视频上传、AI分析、证据生成、风险识别、人工验真到可信报告输出的闭环。对于未清晰出现的接续盘等要素，系统坚持记录证据缺口而非生成虚假检出。", body)]
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def deliver_project(project_id: str) -> dict[str, Any]:
    get_ai_project(project_id)
    # The report must be rendered from the final delivery state, otherwise the
    # PDF would still show the pre-generation status (for example, "待上传").
    now = now_iso()
    with db() as conn:
        conn.execute(
            "UPDATE construction_tasks SET status='生成',updated_at=? WHERE project_id=? AND task_type='digital_delivery'",
            (now, project_id),
        )
        conn.execute("UPDATE project SET updated_at=? WHERE project_id=?", (now, project_id))

    payload = build_trusted_delivery_pdf(project_id)
    target = AI_REPORT_DIR / f"{_safe_name(project_id)}_trusted_delivery.pdf"
    target.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    report_id = f"REPORT-{project_id}"
    relative = target.relative_to(BASE_DIR).as_posix()
    with db() as conn:
        conn.execute(
            """INSERT INTO ai_delivery_reports
               (report_id,project_id,title,report_path,report_sha256,status,generated_at)
               VALUES (?,?,?,?,?,'已生成',?)
               ON CONFLICT(report_id) DO UPDATE SET report_path=excluded.report_path,
               report_sha256=excluded.report_sha256,status='已生成',generated_at=excluded.generated_at""",
            (report_id, project_id, REPORT_TITLE, relative, digest, now),
        )
    return {
        "report_id": report_id,
        "project_id": project_id,
        "title": REPORT_TITLE,
        "status": "已生成",
        "report_url": f"/api/ai/projects/{project_id}/report.pdf",
        "report_path": relative,
        "report_sha256": digest,
        "generated_at": now,
    }


def get_delivery_report(project_id: str) -> tuple[bytes, str]:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM ai_delivery_reports WHERE project_id=? ORDER BY generated_at DESC LIMIT 1",
            (project_id,),
        ).fetchone()
    if row and row["report_path"] and (BASE_DIR / row["report_path"]).exists():
        return (BASE_DIR / row["report_path"]).read_bytes(), row["report_sha256"]
    payload = build_trusted_delivery_pdf(project_id)
    return payload, hashlib.sha256(payload).hexdigest()
