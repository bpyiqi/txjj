from __future__ import annotations

import json
import mimetypes
import re
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .database import BASE_DIR, DB_PATH, db, initialize_database
from .engine import EVIDENCE_LABELS, candidate_matches, extract_code, infer_evidence_type, now_iso, recompute_object, sync_evidence_issues, synchronize_all
from .exports import build_archive, build_excel, build_pdf
from .ai_routes import router as ai_router
from .management_routes import clear_video_records, router as management_router
from .gis_importer import import_geojson
from .video_sampling import ensure_video_decodable

STATIC_DIR = BASE_DIR / "static"
ASSETS_DIR = BASE_DIR / "assets"
UPLOADS_DIR = BASE_DIR / "uploads"
VIDEO_UPLOADS_DIR = UPLOADS_DIR / "videos"
VIDEO_FRAMES_DIR = UPLOADS_DIR / "video_frames"
for directory in (UPLOADS_DIR, VIDEO_UPLOADS_DIR, VIDEO_FRAMES_DIR):
    directory.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_BYTES = 80 * 1024 * 1024
MAX_VIDEO_BYTES = 300 * 1024 * 1024
VIDEO_FRAME_INTERVAL_SECONDS = 2.0
MAX_EXTRACTED_FRAMES = 900

@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    clear_video_records()
    imported = import_geojson()
    if not imported["changed"] and imported["status"] == "not_available":
        synchronize_all()
    yield


app = FastAPI(title="通信基建施工透明化管理与数字化验真交付系统", version="当前", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class LinkConfirm(BaseModel):
    object_id: str
    confidence_score: float = Field(default=0.95, ge=0.0, le=1.0)
    match_reason: str = "人工确认候选匹配"


class IssueUpdate(BaseModel):
    status: str
    assignee: str | None = None
    due_date: str | None = None
    resolution_note: str | None = None


class CandidateRequest(BaseModel):
    filename: str
    detected_code: str | None = None
    evidence_type: str = "site_overview"
    longitude: float | None = None
    latitude: float | None = None



def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _project() -> dict:
    with db() as conn:
        row = dict(conn.execute("SELECT * FROM project LIMIT 1").fetchone())
    row["workflow"] = _loads(row.pop("workflow_json"), [])
    row["data_governance"] = _loads(row.pop("governance_json"), {})
    return row


def _evidence_url(e: dict) -> str | None:
    rel = e.get("asset_path")
    if not rel:
        return None
    rel = str(rel).replace("\\", "/")
    if rel.startswith("uploads/"):
        return f"/uploads/{rel[len('uploads/'):]}"
    return f"/assets/{rel}"


@app.get("/api/health")
def health() -> dict:
    return {"status":"ok","version":"当前","database":DB_PATH.name}


@app.get("/api/project")
def get_project() -> dict:
    return _project()


@app.get("/api/summary")
def summary() -> dict:
    with db() as conn:
        status_rows = conn.execute("SELECT status,COUNT(*) n FROM objects GROUP BY status").fetchall()
        statuses = {r["status"]:r["n"] for r in status_rows}
        object_total = conn.execute("SELECT COUNT(*) n FROM objects").fetchone()["n"]
        evidence_total = conn.execute("SELECT COUNT(*) n FROM evidence").fetchone()["n"]
        avg = conn.execute("SELECT AVG(completeness) avg FROM verification_results").fetchone()["avg"] or 0
        open_issues = conn.execute("SELECT COUNT(*) n FROM issues WHERE status!='已关闭'").fetchone()["n"]
        high_risk = conn.execute("SELECT COUNT(DISTINCT object_id) n FROM issues WHERE severity='高' AND status!='已关闭' AND object_id IS NOT NULL").fetchone()["n"]
        report_count = conn.execute("SELECT COUNT(*) n FROM evidence WHERE evidence_type IN ('acceptance_report','otdr_report','as_built_document') AND review_status='已确认'").fetchone()["n"]
        issue_dist = [dict(r) for r in conn.execute("SELECT issue_type name,COUNT(*) value FROM issues WHERE status!='已关闭' GROUP BY issue_type ORDER BY value DESC").fetchall()]
        activity = [dict(r) for r in conn.execute("SELECT * FROM activities ORDER BY activity_id DESC LIMIT 8").fetchall()]
        readiness = max(0, min(100, round(avg*80 + min(report_count/(max(object_total,1)*3),1)*10 + (1-min(open_issues/max(object_total*8,1),1))*10)))
        next_obj = conn.execute("""SELECT o.object_id,v.completeness,v.missing_evidence,
            (SELECT COUNT(*) FROM issues i WHERE i.object_id=o.object_id AND i.status!='已关闭') issue_count
            FROM objects o JOIN verification_results v ON o.object_id=v.object_id
            WHERE v.completeness<1 ORDER BY issue_count DESC,v.completeness ASC,o.object_id LIMIT 1""").fetchone()
    recommendation = None
    if next_obj:
        recommendation = {
            "object_id":next_obj["object_id"],
            "title":f"优先处理 {next_obj['object_id']}",
            "description":f"当前完整率 {next_obj['completeness']:.0%}，缺少：{next_obj['missing_evidence']}。",
            "impact":"补齐首个强制证据后可立即触发对象复验和问题闭环。"
        }
    return {
        "project":_project(),
        "kpis":{
            "object_total":object_total,"evidence_total":evidence_total,
            "verified":statuses.get("已验真",0),"partial":statuses.get("部分匹配",0),
            "missing":statuses.get("缺失影像",0),"open_issues":open_issues,
            "archive_completeness":round(avg*100,1),"delivery_readiness":readiness,"high_risk_objects":high_risk
        },
        "status_distribution":[{"name":k,"value":statuses.get(k,0)} for k in ["已验真","部分匹配","缺失影像"]],
        "issue_distribution":issue_dist,"recent_activity":activity,"recommendation":recommendation
    }


@app.get("/api/objects")
def list_objects(status: str | None = None, search: str | None = None) -> list[dict]:
    sql="""SELECT o.*,v.required_count,v.matched_count,v.missing_evidence,v.completeness,v.status verification_status,
           (SELECT COUNT(*) FROM evidence e WHERE e.linked_object_id=o.object_id) evidence_count,
           (SELECT COUNT(*) FROM issues i WHERE i.object_id=o.object_id AND i.status!='已关闭') issue_count
           FROM objects o LEFT JOIN verification_results v ON o.object_id=v.object_id WHERE 1=1"""
    args=[]
    if status:
        sql += " AND v.status=?"; args.append(status)
    if search:
        sql += " AND (o.object_id LIKE ? OR o.object_type LIKE ? OR o.site_id LIKE ?)"; q=f"%{search}%"; args += [q,q,q]
    sql += " ORDER BY o.object_id"
    with db() as conn:
        rows=[dict(r) for r in conn.execute(sql,args).fetchall()]
    for row in rows:
        row["attributes"]=_loads(row.pop("attributes_json"),{})
    return rows


@app.get("/api/objects/{object_id}")
def object_detail(object_id: str) -> dict:
    with db() as conn:
        obj=conn.execute("SELECT * FROM objects WHERE object_id=?",(object_id,)).fetchone()
        if not obj: raise HTTPException(404,"对象不存在")
        obj=dict(obj); obj["attributes"]=_loads(obj.pop("attributes_json"),{})
        result=dict(conn.execute("SELECT * FROM verification_results WHERE object_id=?",(object_id,)).fetchone())
        rules=[dict(r) for r in conn.execute("SELECT * FROM rules ORDER BY sequence").fetchall()]
        evidence=[dict(r) for r in conn.execute("SELECT * FROM evidence WHERE linked_object_id=? ORDER BY captured_at,evidence_id",(object_id,)).fetchall()]
        issues=[dict(r) for r in conn.execute("SELECT * FROM issues WHERE object_id=? ORDER BY CASE severity WHEN '高' THEN 1 WHEN '中' THEN 2 ELSE 3 END,issue_id",(object_id,)).fetchall()]
    present={e["evidence_type"] for e in evidence if e["review_status"]=="已确认"}
    for r in rules:
        r["passed"] = r["evidence_type"] in present
        r["matched_evidence"]=[e["evidence_id"] for e in evidence if e["evidence_type"]==r["evidence_type"] and e["review_status"]=="已确认"]
    for e in evidence: e["url"]=_evidence_url(e)
    timeline=[{"stage":r["stage"],"sequence":r["sequence"],"status":"完成" if r["passed"] else "缺失","evidence":r["matched_evidence"]} for r in rules if r["mandatory"]]
    return {"object":obj,"result":result,"rules":rules,"evidence":evidence,"issues":issues,"timeline":timeline}


@app.get("/api/gis")
def gis() -> dict:
    with db() as conn:
        objects=[dict(r) for r in conn.execute("SELECT object_id,layer,object_type,longitude,latitude,status,site_id,ptc_code FROM objects ORDER BY object_id").fetchall()]
        rows=[dict(r) for r in conn.execute("SELECT * FROM gis_features").fetchall()]
    features=[]
    for row in rows:
        features.append({"feature_id":row["feature_id"],"layer":row["layer"],"geometry_type":row["geometry_type"],"coordinates":_loads(row["coordinates_json"],[]),"status":row["status"],"properties":_loads(row["properties_json"],{})})
    return {"objects":objects,"features":features}


@app.get("/api/rules")
def rules() -> list[dict]:
    with db() as conn: return [dict(r) for r in conn.execute("SELECT * FROM rules ORDER BY sequence").fetchall()]


@app.get("/api/evidence")
def list_evidence(object_id: str | None=None, evidence_type: str | None=None, review_status: str | None=None, search: str | None=None) -> list[dict]:
    sql="SELECT * FROM evidence WHERE 1=1"; args=[]
    if object_id: sql+=" AND linked_object_id=?"; args.append(object_id)
    if evidence_type: sql+=" AND evidence_type=?"; args.append(evidence_type)
    if review_status: sql+=" AND review_status=?"; args.append(review_status)
    if search:
        sql+=" AND (filename LIKE ? OR detected_code LIKE ? OR linked_object_id LIKE ? OR ocr_text LIKE ?)"; q=f"%{search}%"; args += [q,q,q,q]
    sql+=" ORDER BY evidence_id DESC"
    with db() as conn: rows=[dict(r) for r in conn.execute(sql,args).fetchall()]
    for e in rows: e["url"]=_evidence_url(e)
    return rows


@app.get("/api/evidence/{evidence_id}")
def evidence_detail(evidence_id: str) -> dict:
    with db() as conn:
        row=conn.execute("SELECT * FROM evidence WHERE evidence_id=?",(evidence_id,)).fetchone()
        if not row: raise HTTPException(404,"证据不存在")
        e=dict(row)
    e["url"]=_evidence_url(e)
    e["candidates"]=candidate_matches(e["filename"],e.get("detected_code"),e["evidence_type"],e.get("longitude"),e.get("latitude"))
    return e


@app.post("/api/evidence/candidates")
def candidates(req: CandidateRequest) -> list[dict]:
    return candidate_matches(req.filename,req.detected_code,req.evidence_type,req.longitude,req.latitude)


@app.post("/api/evidence/upload")
async def upload_evidence(
    file: UploadFile = File(...),
    source_type: str = Form("现场照片"),
    evidence_type: str | None = Form(None),
    detected_code: str | None = Form(None),
    longitude: float | None = Form(None),
    latitude: float | None = Form(None),
) -> dict:
    ext=Path(file.filename or "upload.bin").suffix.lower()
    allowed={".jpg",".jpeg",".png",".webp",".pdf"}
    if ext not in allowed: raise HTTPException(400,"仅支持 JPG、PNG、WEBP、PDF；视频请先抽帧后上传")
    stamp=re.sub(r"[^0-9]","",now_iso())[:14]
    safe=re.sub(r"[^A-Za-z0-9._-]","_",Path(file.filename or "upload.bin").name)
    stored=f"{stamp}_{uuid4().hex[:8]}_{safe}"
    target=UPLOADS_DIR/stored
    written = 0
    try:
        with target.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "单个证据文件不能超过 80 MB")
                out.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    inferred_type,inferred_label,type_score=infer_evidence_type(file.filename or stored)
    etype=evidence_type or inferred_type
    code=detected_code or extract_code(file.filename or "") or "未识别"
    with db() as conn:
        seq=conn.execute("SELECT COUNT(*) n FROM evidence").fetchone()["n"]+1
        eid=f"E{seq:04d}"
        conn.execute("""INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (eid,file.filename or stored,"pdf" if ext==".pdf" else "image",source_type,code,None,etype,
             EVIDENCE_LABELS.get(etype,inferred_label),"系统建议",type_score,"系统","待确认","文件名解析+规则推断","等待人工确认候选对象",
             code if code!="未识别" else f"文件解析完成；建议证据类型：{EVIDENCE_LABELS.get(etype,inferred_label)}",None,f"uploads/{stored}",latitude,longitude,now_iso()))
        conn.execute("INSERT INTO activities(activity_type,title,description,evidence_id,created_at) VALUES (?,?,?,?,?)",
                     ("证据导入","新增现场证据",file.filename,eid,now_iso()))
    sync_evidence_issues()
    result=evidence_detail(eid)
    return result


@app.post("/api/evidence/upload-video")
async def upload_video_and_extract_frames(
    file: UploadFile = File(...),
    evidence_type: str | None = Form(None),
    detected_code: str | None = Form(None),
) -> dict:
    """Upload one MP4, extract one key frame every two seconds, and register each frame as evidence."""
    ext = Path(file.filename or "video.mp4").suffix.lower()
    if ext != ".mp4":
        raise HTTPException(400, "视频抽帧仅支持 MP4 文件")

    stamp = re.sub(r"[^0-9]", "", now_iso())[:14]
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", Path(file.filename or "video.mp4").name)
    video_stored = f"{stamp}_{uuid4().hex[:8]}_{safe}"
    video_target = VIDEO_UPLOADS_DIR / video_stored
    written = 0
    try:
        with video_target.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > MAX_VIDEO_BYTES:
                    raise HTTPException(413, "单个 MP4 文件不能超过 300 MB")
                out.write(chunk)
    except Exception:
        video_target.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    try:
        ensure_video_decodable(video_target)
        import cv2
    except ImportError as exc:
        video_target.unlink(missing_ok=True)
        raise HTTPException(500, "缺少视频处理组件 opencv-python-headless，请重新运行依赖安装") from exc
    except ValueError as exc:
        video_target.unlink(missing_ok=True)
        raise HTTPException(400, str(exc)) from exc

    cap = cv2.VideoCapture(str(video_target))
    if not cap.isOpened():
        video_target.unlink(missing_ok=True)
        raise HTTPException(400, "MP4 无法解码，请确认文件未损坏且编码格式受支持")

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration_seconds = (total_frames / fps) if fps > 0 and total_frames > 0 else 0.0
    if duration_seconds <= 0:
        cap.release()
        video_target.unlink(missing_ok=True)
        raise HTTPException(400, "无法读取视频时长或帧率")

    timestamps: list[float] = []
    t = 0.0
    while t < duration_seconds and len(timestamps) < MAX_EXTRACTED_FRAMES:
        timestamps.append(t)
        t += VIDEO_FRAME_INTERVAL_SECONDS

    inferred_type, inferred_label, type_score = infer_evidence_type(file.filename or video_stored)
    etype = evidence_type or inferred_type
    code = detected_code or extract_code(file.filename or "") or "未识别"
    frame_records: list[dict] = []
    extracted_files: list[Path] = []

    try:
        with db() as conn:
            seq = conn.execute("SELECT COUNT(*) n FROM evidence").fetchone()["n"] + 1
            for index, timestamp_seconds in enumerate(timestamps, start=1):
                cap.set(cv2.CAP_PROP_POS_MSEC, timestamp_seconds * 1000.0)
                ok, frame = cap.read()
                if not ok or frame is None:
                    continue
                millis = int(round(timestamp_seconds * 1000))
                frame_filename = f"{Path(safe).stem}_frame_{index:04d}_t{millis:08d}ms.jpg"
                frame_target = VIDEO_FRAMES_DIR / frame_filename
                encoded_ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                if not encoded_ok:
                    continue
                encoded.tofile(str(frame_target))
                extracted_files.append(frame_target)
                eid = f"E{seq:04d}"
                seq += 1
                mm, ss = divmod(int(timestamp_seconds), 60)
                hh, mm = divmod(mm, 60)
                timecode = f"{hh:02d}:{mm:02d}:{ss:02d}"
                conn.execute(
                    """INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        eid,
                        frame_filename,
                        "video_frame",
                        "视频帧",
                        code,
                        None,
                        etype,
                        EVIDENCE_LABELS.get(etype, inferred_label),
                        "系统建议",
                        type_score,
                        "系统",
                        "待确认",
                        "MP4每2秒抽帧+规则推断",
                        "关键帧已生成，等待人工确认关联对象",
                        f"来源视频：{file.filename or video_stored}；采样时间：{timecode}；抽帧间隔：2秒",
                        None,
                        f"uploads/video_frames/{frame_filename}",
                        None,
                        None,
                        now_iso(),
                    ),
                )
                conn.execute(
                    "INSERT INTO activities(activity_type,title,description,evidence_id,created_at) VALUES (?,?,?,?,?)",
                    ("视频抽帧", "视频关键帧已入库", f"{file.filename} @ {timecode}", eid, now_iso()),
                )
                frame_records.append({"evidence_id": eid, "timestamp_seconds": timestamp_seconds})
    except Exception:
        for extracted in extracted_files:
            extracted.unlink(missing_ok=True)
        video_target.unlink(missing_ok=True)
        raise
    finally:
        cap.release()

    if not frame_records:
        video_target.unlink(missing_ok=True)
        raise HTTPException(400, "视频未能提取有效关键帧")

    sync_evidence_issues()
    frames = [evidence_detail(item["evidence_id"]) for item in frame_records]
    return {
        "video_filename": file.filename or video_stored,
        "stored_video": f"uploads/videos/{video_stored}",
        "interval_seconds": VIDEO_FRAME_INTERVAL_SECONDS,
        "duration_seconds": round(duration_seconds, 3),
        "source_frame_count": total_frames,
        "extracted_frame_count": len(frames),
        "frames": frames,
    }


@app.post("/api/evidence/{evidence_id}/confirm-link")
def confirm_link(evidence_id: str, req: LinkConfirm) -> dict:
    with db() as conn:
        ev=conn.execute("SELECT * FROM evidence WHERE evidence_id=?",(evidence_id,)).fetchone()
        if not ev: raise HTTPException(404,"证据不存在")
        obj=conn.execute("SELECT object_id FROM objects WHERE object_id=?",(req.object_id,)).fetchone()
        if not obj: raise HTTPException(404,"工程对象不存在")
        previous=ev["linked_object_id"]
        conn.execute("""UPDATE evidence SET linked_object_id=?,confidence_label='人工确认',confidence_score=?,verified_by='人工',
                     review_status='已确认',match_method='候选匹配+人工确认',match_reason=? WHERE evidence_id=?""",
                     (req.object_id,req.confidence_score,req.match_reason,evidence_id))
        conn.execute("INSERT INTO activities(activity_type,title,description,object_id,evidence_id,created_at) VALUES (?,?,?,?,?,?)",
                     ("关联确认","证据已关联工程对象",f"{evidence_id} → {req.object_id}",req.object_id,evidence_id,now_iso()))
    sync_evidence_issues()
    if previous and previous!=req.object_id: recompute_object(previous)
    result=recompute_object(req.object_id)
    return {"evidence":evidence_detail(evidence_id),"verification":result}


@app.post("/api/objects/{object_id}/reverify")
def reverify(object_id: str) -> dict:
    with db() as conn:
        if not conn.execute("SELECT 1 FROM objects WHERE object_id=?",(object_id,)).fetchone(): raise HTTPException(404,"对象不存在")
        conn.execute("INSERT INTO activities(activity_type,title,description,object_id,created_at) VALUES (?,?,?,?,?)",
                     ("对象复验","规则引擎已重新计算",object_id,object_id,now_iso()))
    return recompute_object(object_id)


@app.get("/api/issues")
def list_issues(issue_type: str | None=None, severity: str | None=None, status: str | None=None, object_id: str | None=None, search: str | None=None) -> list[dict]:
    sql="SELECT * FROM issues WHERE 1=1"; args=[]
    for col,val in [("issue_type",issue_type),("severity",severity),("status",status),("object_id",object_id)]:
        if val: sql+=f" AND {col}=?"; args.append(val)
    if search: sql+=" AND (issue_id LIKE ? OR title LIKE ? OR description LIKE ? OR object_id LIKE ?)"; q=f"%{search}%"; args += [q,q,q,q]
    sql+=" ORDER BY CASE severity WHEN '高' THEN 1 WHEN '中' THEN 2 ELSE 3 END, CASE status WHEN '新发现' THEN 1 WHEN '待确认' THEN 2 WHEN '待整改' THEN 3 WHEN '已补证' THEN 4 ELSE 5 END, issue_id"
    with db() as conn: return [dict(r) for r in conn.execute(sql,args).fetchall()]


@app.patch("/api/issues/{issue_id}")
def update_issue(issue_id: str, req: IssueUpdate) -> dict:
    allowed={"新发现","待确认","待整改","已补证","已关闭"}
    if req.status not in allowed: raise HTTPException(400,"无效的问题状态")
    with db() as conn:
        row=conn.execute("SELECT * FROM issues WHERE issue_id=?",(issue_id,)).fetchone()
        if not row: raise HTTPException(404,"问题不存在")
        conn.execute("UPDATE issues SET status=?,assignee=?,due_date=?,resolution_note=?,updated_at=? WHERE issue_id=?",
                     (req.status,req.assignee,req.due_date,req.resolution_note,now_iso(),issue_id))
        conn.execute("INSERT INTO activities(activity_type,title,description,object_id,created_at) VALUES (?,?,?,?,?)",
                     ("问题处置","问题状态已更新",f"{issue_id} → {req.status}",row["object_id"],now_iso()))
        result=dict(conn.execute("SELECT * FROM issues WHERE issue_id=?",(issue_id,)).fetchone())
    return result


@app.get("/api/exports/excel")
def export_excel() -> Response:
    return Response(build_excel(),media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":"attachment; filename=verification_export.xlsx"})


@app.get("/api/exports/pdf")
def export_pdf() -> Response:
    return Response(build_pdf(),media_type="application/pdf",headers={"Content-Disposition":"attachment; filename=verification_report.pdf"})


@app.get("/api/exports/archive")
def export_archive() -> Response:
    return Response(build_archive(),media_type="application/zip",headers={"Content-Disposition":"attachment; filename=digital_delivery_archive.zip"})


@app.post("/api/admin/reset")
def reset_database() -> dict:
    initialize_database(force=True)
    synchronize_all()
    return {"status":"reset"}


app.include_router(ai_router)
app.include_router(management_router)
app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")
