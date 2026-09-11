from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .ai_platform import (
    analyze_task,
    complete_task,
    create_ai_project,
    create_construction_task,
    dashboard,
    get_task,
    get_delivery_report,
    list_project_tasks,
    new_video_target,
    register_task_video,
    deliver_project,
)
from .yolo_construction import model_status
from .yolo_safety import model_status as safety_model_status


router = APIRouter(prefix="/api/ai", tags=["AI施工智能验真"])
MAX_AI_VIDEO_BYTES = 300 * 1024 * 1024


class AIProjectCreate(BaseModel):
    project_id: str | None = None
    name: str
    scenario: str = "高速公路通信工程光缆施工全过程智能验真"
    location: str = "高速公路通信基础设施施工现场"
    data_version: str = "通信基建施工数据集"


class ConstructionTaskCreate(BaseModel):
    task_id: str | None = None
    project_id: str
    task_type: str
    name: str
    sequence: int = Field(ge=1)
    linked_object_id: str | None = None
    status: str = "待上传"


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(404, str(exc).strip("'"))
    if isinstance(exc, sqlite3.IntegrityError):
        return HTTPException(409, "编号已存在或关联数据无效")
    if isinstance(exc, FileNotFoundError):
        return HTTPException(404, str(exc))
    return HTTPException(400, str(exc))


@router.get("/dashboard")
def ai_dashboard(project_id: str | None = Query(None)) -> dict:
    try:
        return dashboard(project_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/yolo/status")
def yolo_status() -> dict:
    return model_status()


@router.get("/safety/status")
def safety_status() -> dict:
    return safety_model_status()


@router.post("/projects")
def create_project(payload: AIProjectCreate) -> dict:
    try:
        return create_ai_project(payload.model_dump())
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/tasks")
def create_task(payload: ConstructionTaskCreate) -> dict:
    if payload.task_type not in {"air_blowing", "handover", "fusion_splicing", "digital_delivery"}:
        raise HTTPException(400, "不支持的施工任务类型")
    try:
        return create_construction_task(payload.model_dump())
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/projects/{project_id}/tasks")
def project_tasks(project_id: str) -> list[dict]:
    try:
        return list_project_tasks(project_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/tasks/{task_id}")
def task_detail(task_id: str) -> dict:
    try:
        return get_task(task_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/tasks/{task_id}/upload-video")
async def upload_task_video(task_id: str, file: UploadFile = File(...)) -> dict:
    if Path(file.filename or "video.mp4").suffix.lower() != ".mp4":
        raise HTTPException(400, "仅支持 MP4 施工视频")
    target = new_video_target(task_id, file.filename or "video.mp4")
    written = 0
    try:
        with target.open("wb") as stream:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > MAX_AI_VIDEO_BYTES:
                    raise HTTPException(413, "单个施工视频不能超过 300 MB")
                stream.write(chunk)
        return register_task_video(task_id, target)
    except HTTPException:
        target.unlink(missing_ok=True)
        raise
    except Exception as exc:
        target.unlink(missing_ok=True)
        raise _http_error(exc) from exc
    finally:
        await file.close()


@router.post("/tasks/{task_id}/analyze")
def run_ai_analysis(task_id: str) -> dict:
    try:
        return analyze_task(task_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/tasks/{task_id}/complete")
def finish_task(task_id: str) -> dict:
    try:
        return complete_task(task_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/projects/{project_id}/deliver")
def deliver_project_report(project_id: str) -> dict:
    try:
        return deliver_project(project_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/projects/{project_id}/report.pdf")
def download_report(project_id: str) -> Response:
    try:
        payload, digest = get_delivery_report(project_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    return Response(
        payload,
        media_type="application/pdf",
        headers={
            "Content-Disposition": "attachment; filename=trusted_delivery_report.pdf",
            "X-Report-SHA256": digest,
        },
    )
