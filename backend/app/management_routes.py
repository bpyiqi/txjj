from __future__ import annotations

import json
import hashlib
import re
import sqlite3
from pathlib import Path
from uuid import uuid4

import cv2
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, UploadFile

from .ai_platform import analyze_task, register_task_video
from .database import BASE_DIR, db
from .engine import now_iso, synchronize_all
from .gis_importer import import_geojson, import_status
from .yolo_construction import model_status
from .yolo_safety import model_status as safety_model_status
from .video_sampling import ensure_video_decodable


router = APIRouter(prefix="/api/management", tags=["施工透明化管理"])
DATA_DIR = BASE_DIR / "uploads" / "construction_data"
PREVIEW_DIR = BASE_DIR / "uploads" / "browser_previews"
DATA_DIR.mkdir(parents=True, exist_ok=True)
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
MAX_BYTES = 300 * 1024 * 1024
EXTENSIONS = {
    ".mp4": "施工视频",
    ".jpg": "现场图片", ".jpeg": "现场图片", ".png": "现场图片", ".webp": "现场图片",
    ".pdf": "工程资料", ".xls": "工程资料", ".xlsx": "工程资料", ".csv": "工程资料",
    ".geojson": "空间数据", ".zip": "空间数据", ".shp": "空间数据",
    ".dbf": "空间数据", ".shx": "空间数据", ".prj": "空间数据",
}


def _project_id(project_id: str | None) -> str:
    if project_id:
        return project_id
    with db() as conn:
        row = conn.execute(
            """SELECT p.project_id FROM project p
               WHERE EXISTS (SELECT 1 FROM construction_tasks t WHERE t.project_id=p.project_id)
               ORDER BY p.updated_at DESC,p.rowid DESC LIMIT 1"""
        ).fetchone()
    if not row:
        raise HTTPException(404, "暂无施工项目")
    return row["project_id"]


@router.get("/dashboard")
def management_dashboard(project_id: str | None = Query(None)) -> dict:
    pid = _project_id(project_id)
    with db() as conn:
        project = conn.execute("SELECT project_id,name,location FROM project WHERE project_id=?", (pid,)).fetchone()
        if not project:
            raise HTTPException(404, "项目不存在")
        counts = conn.execute(
            """SELECT
               (SELECT COUNT(*) FROM construction_tasks WHERE project_id=?) task_count,
               (SELECT COUNT(*) FROM construction_data d JOIN construction_tasks t ON t.task_id=d.task_id
                WHERE t.project_id=? AND d.data_type IN ('施工视频','现场图片')) media_count,
               (SELECT COUNT(*) FROM construction_data d JOIN construction_tasks t ON t.task_id=d.task_id
                WHERE t.project_id=? AND d.data_type='施工视频' AND d.status='已分析') analysis_count,
               (SELECT COUNT(*) FROM ai_delivery_reports WHERE project_id=?) delivery_count,
               (SELECT COUNT(*) FROM construction_data d JOIN construction_tasks t ON t.task_id=d.task_id
                WHERE t.project_id=? AND d.data_type='施工视频' AND d.status IN ('排队中','抽帧中','YOLO检测中','验真中')) processing_count,
               (SELECT COUNT(*) FROM construction_data d JOIN construction_tasks t ON t.task_id=d.task_id
                WHERE t.project_id=? AND d.data_type='施工视频' AND d.status='分析失败') failed_count""",
            (pid, pid, pid, pid, pid, pid),
        ).fetchone()
    return {"project": dict(project), "statistics": dict(counts)}


@router.get("/platform-overview")
def platform_overview(project_id: str | None = Query(None)) -> dict:
    """Return one read-only view of the real data behind the five platform layers."""
    pid = _project_id(project_id)
    vision = model_status()
    safety = safety_model_status()
    with db() as conn:
        counts = dict(conn.execute(
            """SELECT
               (SELECT COUNT(*) FROM engineering_objects) object_count,
               (SELECT COUNT(*) FROM construction_data d JOIN construction_tasks t ON t.task_id=d.task_id
                WHERE t.project_id=?) collected_count,
               (SELECT COUNT(*) FROM construction_data d JOIN construction_tasks t ON t.task_id=d.task_id
                WHERE t.project_id=? AND d.data_type='施工视频' AND d.status='已分析') analyzed_video_count,
               (SELECT COUNT(*) FROM evidence e LEFT JOIN construction_task_evidence te ON te.evidence_id=e.evidence_id
                LEFT JOIN construction_tasks t ON t.task_id=te.task_id
                WHERE te.evidence_id IS NULL OR t.project_id=?) evidence_count,
               (SELECT COUNT(*) FROM issues WHERE status!='已关闭') open_issue_count,
               (SELECT COUNT(*) FROM ai_delivery_reports WHERE project_id=?) delivery_count,
               (SELECT COUNT(*) FROM evidence WHERE COALESCE(ocr_text,'')!='' OR COALESCE(detected_code,'') NOT IN ('','未识别')) ocr_result_count,
               (SELECT COUNT(*) FROM gis_features) gis_feature_count""",
            (pid, pid, pid, pid),
        ).fetchone())
        reports = [dict(row) for row in conn.execute(
            """SELECT report_id,title,status,generated_at,report_sha256
               FROM ai_delivery_reports WHERE project_id=? ORDER BY generated_at DESC""", (pid,)
        ).fetchall()]
        safety_result_count = conn.execute(
            """SELECT COUNT(*) FROM ai_analysis_results ar JOIN construction_tasks t ON t.task_id=ar.task_id
               WHERE t.project_id=? AND ar.detected_objects_json LIKE '%\"source_class\"%'""",
            (pid,),
        ).fetchone()[0]
    return {
        "project_id": pid,
        "layers": counts,
        "engines": {
            "construction_vision": {
                "status": "可运行" if vision.get("runtime_available") and vision.get("weights_available") else "未就绪",
                "result_count": counts["analyzed_video_count"],
            },
            "safety_supervision": {
                "status": "可运行" if safety.get("runtime_available") and safety.get("weights_available") else "等待训练",
                "result_count": safety_result_count,
            },
            "engineering_ocr": {
                "status": "已有识别结果" if counts["ocr_result_count"] else "待采集",
                "result_count": counts["ocr_result_count"],
            },
        },
        "reports": reports,
    }


@router.get("/projects")
def projects() -> list[dict]:
    with db() as conn:
        return [dict(row) for row in conn.execute(
            "SELECT project_id,name,location FROM project WHERE EXISTS (SELECT 1 FROM construction_tasks t WHERE t.project_id=project.project_id) ORDER BY updated_at DESC"
        ).fetchall()]


@router.get("/tasks")
def tasks(project_id: str | None = Query(None)) -> list[dict]:
    pid = _project_id(project_id)
    with db() as conn:
        return [dict(row) for row in conn.execute(
            """SELECT task_id,project_id,name,task_type,status,sequence,linked_object_id
               FROM construction_tasks WHERE project_id=? ORDER BY sequence""", (pid,)
        ).fetchall()]


@router.get("/construction-data")
def construction_data(project_id: str | None = Query(None)) -> list[dict]:
    pid = _project_id(project_id)
    with db() as conn:
        return [dict(row) for row in conn.execute(
            """SELECT d.id,d.task_id,t.name task_name,d.data_type,d.file_name,d.upload_time,d.status,
                      d.progress,d.stage_message,d.error_message,d.started_at,d.completed_at
               FROM construction_data d JOIN construction_tasks t ON t.task_id=d.task_id
               WHERE t.project_id=? ORDER BY d.upload_time DESC,d.id DESC""", (pid,)
        ).fetchall()]


@router.post("/construction-data")
async def upload_construction_data(
    background_tasks: BackgroundTasks,
    project_id: str = Form(...), task_id: str = Form(...), file: UploadFile = File(...)
) -> dict:
    filename = Path(file.filename or "upload.bin").name
    extension = Path(filename).suffix.lower()
    if extension not in EXTENSIONS:
        raise HTTPException(400, "支持视频、图片、工程资料、GeoJSON 和 Shapefile 配套文件")
    with db() as conn:
        task = conn.execute(
            "SELECT task_id FROM construction_tasks WHERE task_id=? AND project_id=?", (task_id, project_id)
        ).fetchone()
    if not task:
        raise HTTPException(400, "施工任务与项目不匹配")
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", filename)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    target = DATA_DIR / f"{uuid4().hex[:10]}_{safe}"
    written = 0
    digest = hashlib.sha256()
    try:
        with target.open("wb") as stream:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > MAX_BYTES:
                    raise HTTPException(413, "单个文件不能超过 300 MB")
                digest.update(chunk)
                stream.write(chunk)
        data_type = EXTENSIONS[extension]
        if data_type == "施工视频":
            converted = ensure_video_decodable(target)
            if converted:
                digest = hashlib.sha256()
                with target.open("rb") as stream:
                    while chunk := stream.read(1024 * 1024):
                        digest.update(chunk)
        gis_result = None
        if extension == ".geojson":
            gis_result = import_geojson(target)
            if gis_result["changed"]:
                synchronize_all()
        initial_status = "排队中" if data_type == "施工视频" else "已入库" if extension == ".geojson" else "已采集"
        initial_progress = 5 if data_type == "施工视频" else 100
        with db() as conn:
            cursor = conn.execute(
                """INSERT INTO construction_data
                   (task_id,data_type,file_name,file_path,upload_time,status,progress,stage_message,file_sha256)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (task_id, data_type, filename, target.relative_to(BASE_DIR).as_posix(), now_iso(),
                 initial_status, initial_progress,
                 "等待后台处理" if data_type == "施工视频" else
                 f"已导入 {gis_result['feature_count']} 个空间对象" if gis_result else "采集完成",
                 digest.hexdigest()),
            )
            data_id = cursor.lastrowid
        if data_type == "施工视频":
            background_tasks.add_task(_process_analysis_job, data_id)
        return {"id": data_id, "analysis_job_id": data_id if data_type == "施工视频" else None,
                "task_id": task_id, "data_type": data_type, "file_name": filename,
                "status": initial_status, "progress": initial_progress, "gis_import": gis_result}
    except ValueError as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(400, str(exc)) from exc
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        await file.close()


def _set_analysis_status(data_id: int, status: str, progress: int, message: str,
                         error: str | None = None, *, started: bool = False,
                         completed: bool = False) -> None:
    with db() as conn:
        conn.execute(
            """UPDATE construction_data SET status=?,progress=?,stage_message=?,error_message=?,
                      started_at=CASE WHEN ? THEN COALESCE(started_at,?) ELSE started_at END,
                      completed_at=CASE WHEN ? THEN ? ELSE completed_at END
               WHERE id=?""",
            (status, progress, message, error, int(started), now_iso(), int(completed), now_iso(), data_id),
        )


def _process_analysis_job(data_id: int) -> None:
    with db() as conn:
        row = conn.execute("SELECT * FROM construction_data WHERE id=?", (data_id,)).fetchone()
    if not row:
        return
    if row["data_type"] != "施工视频":
        _set_analysis_status(data_id, "分析失败", 0, "文件类型不支持", "只有施工视频可执行影像分析", completed=True)
        return
    path = BASE_DIR / row["file_path"]
    try:
        _set_analysis_status(data_id, "抽帧中", 20, "正在解析视频并提取关键帧", started=True)
        register_task_video(row["task_id"], path)
        _set_analysis_status(data_id, "YOLO检测中", 55, "正在识别施工目标并生成检测框")
        analyze_task(row["task_id"], data_id=data_id)
        _set_analysis_status(data_id, "验真中", 85, "正在匹配施工工序与工程验收规则")
        with db() as conn:
            evidence_count = conn.execute(
                "SELECT COUNT(*) n FROM ai_analysis_results WHERE data_id=?", (data_id,)
            ).fetchone()["n"]
        _set_analysis_status(data_id, "已分析", 100, f"分析与验真完成，共生成 {evidence_count} 帧证据", completed=True)
    except Exception as exc:
        _set_analysis_status(data_id, "分析失败", 0, "后台处理失败", str(exc).strip("'"), completed=True)


@router.post("/construction-data/{data_id}/analyze")
def analyze_construction_data(data_id: int) -> dict:
    with db() as conn:
        row = conn.execute("SELECT * FROM construction_data WHERE id=?", (data_id,)).fetchone()
    if not row:
        raise HTTPException(404, "采集数据不存在")
    if row["data_type"] != "施工视频":
        raise HTTPException(400, "只有施工视频可执行影像分析")
    _process_analysis_job(data_id)
    with db() as conn:
        current = conn.execute("SELECT status,error_message FROM construction_data WHERE id=?", (data_id,)).fetchone()
        evidence_count = conn.execute("SELECT COUNT(*) n FROM ai_analysis_results WHERE data_id=?", (data_id,)).fetchone()["n"]
    if current["status"] == "分析失败":
        raise HTTPException(400, current["error_message"] or "影像分析失败")
    return {"id": data_id, "task_id": row["task_id"], "status": current["status"], "evidence_count": evidence_count}


@router.get("/analysis-tasks")
def analysis_tasks(project_id: str | None = Query(None)) -> list[dict]:
    pid = _project_id(project_id)
    with db() as conn:
        task_rows = conn.execute(
            """SELECT d.id analysis_job_id,d.task_id,t.name,t.task_type,t.linked_object_id,
                      d.status,d.progress,d.stage_message,d.error_message,d.file_name video_file,
                      d.file_path source_video_path,d.file_sha256 source_video_sha256,
                      d.upload_time,d.started_at,d.completed_at,
                      COUNT(DISTINCT ar.analysis_id) evidence_count
               FROM construction_data d
               JOIN construction_tasks t ON t.task_id=d.task_id
               LEFT JOIN ai_analysis_results ar ON ar.data_id=d.id
               WHERE t.project_id=? AND d.data_type='施工视频'
               GROUP BY d.id ORDER BY d.upload_time DESC,d.id DESC""", (pid,)
        ).fetchall()
        result = []
        for task in task_rows:
            analyses = conn.execute(
                "SELECT stage,detected_objects_json,risk_json,acceptance_rule_json FROM ai_analysis_results WHERE data_id=? ORDER BY created_at,analysis_id",
                (task["analysis_job_id"],),
            ).fetchall()
            stages = list(dict.fromkeys(row["stage"] for row in analyses))
            item = dict(task)
            objects = [
                detected.get("label", "未知对象") if isinstance(detected, dict) else detected
                for row in analyses for detected in json.loads(row["detected_objects_json"])
            ]
            object_counts = {label: objects.count(label) for label in sorted(set(objects))}
            scenes = [
                json.loads(row["acceptance_rule_json"] or "{}").get("detected_scene")
                for row in analyses
            ]
            result.append({
                **item,
                "stages": stages,
                "completed_count": len(stages),
                "total_stage_count": 4 if task["task_type"] == "air_blowing" else 5,
                "risk_count": sum(len(json.loads(row["risk_json"] or "[]")) for row in analyses),
                "detected_objects": sorted(set(objects)),
                "detected_object_counts": object_counts,
                "detected_scene": next((scene for scene in scenes if scene), None),
            })
    return result


def _media_url(asset_path: str | None) -> str | None:
    asset = (asset_path or "").replace("\\", "/")
    if not asset:
        return None
    if asset.startswith("uploads/"):
        return f"/uploads/{asset.removeprefix('uploads/')}"
    return f"/assets/{asset}"


def _browser_video_preview(task_id: str, source_video_path: str | None, digest: str | None) -> str | None:
    if not source_video_path:
        return None
    source = BASE_DIR / source_video_path
    if not source.exists():
        return None
    probe = cv2.VideoCapture(str(source))
    try:
        fourcc = int(probe.get(cv2.CAP_PROP_FOURCC))
        codec = "".join(chr((fourcc >> (8 * index)) & 0xFF) for index in range(4)).lower()
    finally:
        probe.release()
    if codec in {"h264", "avc1"}:
        return source_video_path.replace("\\", "/")
    safe_task = re.sub(r"[^A-Za-z0-9._-]", "_", task_id)
    target = PREVIEW_DIR / f"{safe_task}_{(digest or 'video')[:12]}.webm"
    if target.exists() and target.stat().st_size > 0:
        return target.relative_to(BASE_DIR).as_posix()

    temporary = target.with_name(f"{target.stem}.building.webm")
    capture = cv2.VideoCapture(str(source))
    writer = None
    frame_count = 0
    try:
        if not capture.isOpened():
            return None
        fps = capture.get(cv2.CAP_PROP_FPS) or 5.0
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if width < 1 or height < 1:
            return None
        writer = cv2.VideoWriter(
            str(temporary), cv2.VideoWriter_fourcc(*"VP80"), fps, (width, height)
        )
        if not writer.isOpened():
            return None
        while True:
            ok, frame = capture.read()
            if not ok or frame is None:
                break
            writer.write(frame)
            frame_count += 1
    finally:
        capture.release()
        if writer is not None:
            writer.release()

    if frame_count < 1 or not temporary.exists() or temporary.stat().st_size == 0:
        temporary.unlink(missing_ok=True)
        return None
    temporary.replace(target)
    return target.relative_to(BASE_DIR).as_posix()


def _analysis_visualization(task_id: str, data_id: int | None = None) -> dict:
    with db() as conn:
        if data_id is None:
            data = conn.execute(
                """SELECT * FROM construction_data
                   WHERE task_id=? AND data_type='施工视频'
                   ORDER BY upload_time DESC,id DESC LIMIT 1""", (task_id,)
            ).fetchone()
        else:
            data = conn.execute(
                "SELECT * FROM construction_data WHERE id=? AND task_id=? AND data_type='施工视频'",
                (data_id, task_id),
            ).fetchone()
        if not data:
            raise HTTPException(404, "尚未上传施工视频，分析任务不存在")
        data_id = data["id"]
        task = conn.execute(
            """SELECT task_id,project_id,name,task_type,status,linked_object_id,
                      source_video_path,source_video_sha256,updated_at
               FROM construction_tasks WHERE task_id=?""",
            (task_id,),
        ).fetchone()
        if not task:
            raise HTTPException(404, "施工任务不存在")
        rows = conn.execute(
            """SELECT ar.analysis_id,ar.evidence_id,ar.stage,ar.confidence,
                      ar.detected_objects_json,ar.risk_json,ar.engineering_object_json,
                      ar.acceptance_rule_json,ar.evidence_hash,ar.model_name,
                      ar.model_version,ar.review_status,ar.created_at,
                      e.filename,e.asset_path,e.media_type,te.source_timestamp
               FROM ai_analysis_results ar
               JOIN evidence e ON e.evidence_id=ar.evidence_id
               LEFT JOIN construction_task_evidence te
                 ON te.task_id=ar.task_id AND te.evidence_id=ar.evidence_id
               WHERE ar.data_id=?
               ORDER BY te.source_timestamp,ar.created_at,ar.analysis_id""",
            (data_id,),
        ).fetchall()

    frames = []
    stage_status: dict[str, str] = {}
    all_risks = []
    for row in rows:
        detected = json.loads(row["detected_objects_json"] or "[]")
        risks = json.loads(row["risk_json"] or "[]")
        engineering_object = json.loads(row["engineering_object_json"] or "{}")
        rule = json.loads(row["acceptance_rule_json"] or "{}")
        detected_labels = {
            item.get("label") if isinstance(item, dict) else str(item)
            for item in detected
        }
        required = list(rule.get("required_evidence") or [])
        matched = [label for label in required if label in detected_labels]
        missing = [label for label in required if label not in detected_labels]
        verdict = "风险提示" if risks else "证据匹配" if not missing else "待补证"
        stage_status[row["stage"]] = row["review_status"] or "待人工验真"
        all_risks.extend(risks)
        frames.append({
            "analysis_id": row["analysis_id"],
            "evidence_id": row["evidence_id"],
            "timestamp": row["source_timestamp"],
            "filename": row["filename"],
            "frame_url": _media_url(row["asset_path"]),
            "media_type": row["media_type"],
            "stage": row["stage"],
            "confidence": row["confidence"],
            "detected_objects": detected,
            "risk": risks,
            "engineering_object": engineering_object,
            "acceptance_rule": rule,
            "required_labels": required,
            "matched_labels": matched,
            "missing_labels": missing,
            "frame_verdict": verdict,
            "evidence_hash": row["evidence_hash"],
            "model_name": row["model_name"],
            "model_version": row["model_version"],
            "review_status": row["review_status"],
            "created_at": row["created_at"],
        })

    expected_count = 4 if task["task_type"] == "air_blowing" else 5
    processing_statuses = {"排队中", "抽帧中", "YOLO检测中", "验真中"}
    conclusion = (
        data["status"] if data["status"] in processing_statuses | {"分析失败"}
        else "待补证" if len(stage_status) < expected_count
        else "部分通过" if all_risks or any(status != "验真完成" for status in stage_status.values())
        else "通过"
    )
    task_payload = dict(task)
    task_payload.pop("source_video_path")
    source_video_path = data["file_path"]
    task_payload["source_video_sha256"] = data["file_sha256"] or task_payload.get("source_video_sha256")
    task_payload.update({
        "analysis_job_id": data_id,
        "status": data["status"],
        "progress": data["progress"],
        "stage_message": data["stage_message"],
        "error_message": data["error_message"],
        "video_file": data["file_name"],
        "upload_time": data["upload_time"],
    })
    original_video_url = _media_url(source_video_path)
    preview_path = _browser_video_preview(
        task_payload["task_id"], source_video_path, task_payload.get("source_video_sha256")
    )
    task_payload["original_video_url"] = original_video_url
    task_payload["video_url"] = _media_url(preview_path) or original_video_url
    task_payload["video_preview_generated"] = bool(
        preview_path and preview_path.replace("\\", "/") != (source_video_path or "").replace("\\", "/")
    )
    return {
        "task": task_payload,
        "pipeline": ["upload", "frames", "detection", "result", "verification"],
        "frames": frames,
        "summary": {
            "frame_count": len(frames),
            "boxed_frame_count": sum(
                any(isinstance(item, dict) and item.get("bbox_xyxy") for item in frame["detected_objects"])
                for frame in frames
            ),
            "detected_object_count": sum(len(frame["detected_objects"]) for frame in frames),
            "completed_stage_count": len(stage_status),
            "total_stage_count": expected_count,
            "risk_count": len(all_risks),
            "conclusion": conclusion,
        },
    }


@router.get("/analysis-jobs/{data_id}/visualization")
def analysis_job_visualization(data_id: int) -> dict:
    with db() as conn:
        row = conn.execute("SELECT task_id FROM construction_data WHERE id=?", (data_id,)).fetchone()
    if not row:
        raise HTTPException(404, "分析任务不存在")
    return _analysis_visualization(row["task_id"], data_id)


@router.get("/analysis-tasks/{task_id}/visualization")
def analysis_visualization(task_id: str) -> dict:
    return _analysis_visualization(task_id)


@router.get("/verification-workbench")
def verification_workbench(project_id: str | None = Query(None)) -> list[dict]:
    pid = _project_id(project_id)
    with db() as conn:
        rows = conn.execute(
            """SELECT t.task_id,t.name,t.task_type,t.status,ar.stage,ar.risk_json,ar.review_status
               FROM construction_tasks t LEFT JOIN ai_analysis_results ar ON ar.task_id=t.task_id
               WHERE t.project_id=? AND t.task_type IN ('air_blowing','fusion_splicing')
               ORDER BY t.sequence,ar.created_at,ar.analysis_id""", (pid,)
        ).fetchall()
    grouped: dict[str, dict] = {}
    for row in rows:
        item = grouped.setdefault(row["task_id"], {"task_id": row["task_id"], "name": row["name"], "task_type": row["task_type"], "status": row["status"], "stages": {}, "risks": []})
        if row["stage"]:
            item["stages"][row["stage"]] = row["review_status"] or "待验真"
            item["risks"].extend(json.loads(row["risk_json"] or "[]"))
    for item in grouped.values():
        item["evidence_count"] = len([row for row in rows if row["task_id"] == item["task_id"] and row["stage"]])
        item["completed_count"] = len(item["stages"])
        item["total_stage_count"] = 4 if item["task_type"] == "air_blowing" else 5
        item["conclusion"] = (
            "待补证" if item["completed_count"] < item["total_stage_count"]
            else "部分通过" if item["risks"] or any(status != "验真完成" for status in item["stages"].values())
            else "通过"
        )
    return list(grouped.values())


@router.get("/evidence")
def evidence(project_id: str | None = Query(None)) -> list[dict]:
    pid = _project_id(project_id)
    with db() as conn:
        rows = conn.execute(
            """SELECT DISTINCT e.evidence_id,e.filename,e.asset_path,e.media_type,e.source_type,e.captured_at,e.created_at,
               e.review_status,e.linked_object_id,t.task_id,t.name task_name,
               COALESCE(ar.stage,e.evidence_label) stage,eo.name object_name
               FROM evidence e
               LEFT JOIN construction_task_evidence te ON te.evidence_id=e.evidence_id
               LEFT JOIN construction_tasks t ON t.task_id=te.task_id AND t.project_id=?
               LEFT JOIN ai_analysis_results ar ON ar.evidence_id=e.evidence_id
               LEFT JOIN engineering_objects eo ON eo.id=e.linked_object_id
               WHERE te.evidence_id IS NULL OR t.task_id IS NOT NULL
               ORDER BY e.created_at DESC,e.evidence_id""", (pid,)
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["url"] = _media_url(item.pop("asset_path"))
        result.append(item)
    return result


@router.get("/engineering-objects")
def engineering_objects() -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """SELECT eo.id,eo.name,eo.type,eo.location,eo.status,
               COALESCE(o.layer,eo.type) layer,COALESCE(o.object_type,eo.type) object_type,
               o.geometry_type,o.longitude,o.latitude,o.source_file,
               gf.coordinates_json,gf.properties_json,o.attributes_json,
               COALESCE(v.status,'缺失影像') verification_status,COALESCE(v.completeness,0) completeness,
               COUNT(DISTINCT t.task_id) task_count,COUNT(DISTINCT te.evidence_id) evidence_count,
               GROUP_CONCAT(DISTINCT t.name) task_names
               FROM engineering_objects eo
               LEFT JOIN objects o ON o.object_id=eo.id
               LEFT JOIN gis_features gf ON gf.feature_id=o.object_id AND gf.layer=o.layer
               LEFT JOIN verification_results v ON v.object_id=eo.id
               LEFT JOIN construction_tasks t ON t.linked_object_id=eo.id
               LEFT JOIN construction_task_evidence te ON te.task_id=t.task_id
               GROUP BY eo.id ORDER BY eo.id"""
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["geometry"] = json.loads(item.pop("coordinates_json") or "null")
        item["design_attributes"] = json.loads(item.pop("properties_json") or item.pop("attributes_json") or "{}")
        item.pop("attributes_json", None)
        result.append(item)
    return result


@router.get("/gis/status")
def gis_status() -> dict:
    return import_status()


@router.post("/gis/import")
def gis_import() -> dict:
    result = import_geojson()
    if result["changed"]:
        synchronize_all()
    result["database"] = import_status()
    return result
