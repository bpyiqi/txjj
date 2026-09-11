from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.video_sampling import read_key_frames
from backend.app.video_sampling import ensure_video_decodable
from backend.app.yolo_construction import model_status


def test_video_sampling_falls_back_when_duration_metadata_is_missing(monkeypatch):
    import cv2

    class MetadataFreeCapture:
        def __init__(self, _path):
            self.index = 0

        def isOpened(self):
            return True

        def get(self, _property):
            return 0

        def read(self):
            if self.index == 20:
                return False, None
            self.index += 1
            return True, object()

        def release(self):
            return None

    monkeypatch.setattr(cv2, "VideoCapture", MetadataFreeCapture)
    frames = read_key_frames(Path("metadata-free.mp4"), 4)
    assert len(frames) == 4
    assert [timestamp for timestamp, _ in frames] == sorted(timestamp for timestamp, _ in frames)


def test_video_codec_is_normalized_when_opencv_rejects_it(tmp_path, monkeypatch):
    import cv2

    source = Path("demo_air_blowing/input/BV1u2Mv6METn.mp4")
    target = tmp_path / "mobile-codec.mp4"
    target.write_bytes(source.read_bytes())
    real_capture = cv2.VideoCapture
    calls = 0

    class RejectedCapture:
        def isOpened(self):
            return False

        def release(self):
            return None

    def capture(path):
        nonlocal calls
        calls += 1
        return RejectedCapture() if calls == 1 else real_capture(path)

    monkeypatch.setattr(cv2, "VideoCapture", capture)
    assert ensure_video_decodable(target) is True
    check = real_capture(str(target))
    try:
        ok, frame = check.read()
        assert ok and frame is not None
    finally:
        check.release()


def test_video_initialization_segment_is_rejected_with_exact_reason(tmp_path):
    target = tmp_path / "segment.mp4"
    target.write_bytes(b"\x00\x00\x00\x18ftypiso5" + b"\x00" * 900 + b"moov")
    try:
        ensure_video_decodable(target)
    except ValueError as exc:
        assert "只包含视频初始化信息" in str(exc)
        assert "不包含可分析画面" in str(exc)
    else:
        raise AssertionError("初始化片段不应作为完整视频接收")


def test_management_collection_analysis_and_views():
    with TestClient(app) as client:
        assert client.post("/api/admin/reset").status_code == 200
        dashboard = client.get("/api/management/dashboard").json()
        project_id = dashboard["project"]["project_id"]
        tasks = client.get("/api/management/tasks", params={"project_id": project_id}).json()
        air_task = next(task for task in tasks if task["task_type"] == "air_blowing")

        video = Path("demo_air_blowing/input/BV1u2Mv6METn.mp4")
        with video.open("rb") as stream:
            uploaded = client.post(
                "/api/management/construction-data",
                data={"project_id": project_id, "task_id": air_task["task_id"]},
                files={"file": (video.name, stream, "video/mp4")},
            )
        assert uploaded.status_code == 200, uploaded.text
        assert uploaded.json()["status"] == "排队中"
        assert uploaded.json()["analysis_job_id"] == uploaded.json()["id"]
        collected = client.get("/api/management/construction-data", params={"project_id": project_id}).json()
        assert collected[0]["status"] == "已分析"
        assert collected[0]["progress"] == 100

        stats = client.get("/api/management/dashboard", params={"project_id": project_id}).json()["statistics"]
        assert stats == {"task_count": 4, "media_count": 1, "analysis_count": 1,
                         "delivery_count": 0, "processing_count": 0, "failed_count": 0}
        evidence = client.get("/api/management/evidence", params={"project_id": project_id}).json()
        assert len(evidence) >= 65
        assert sum(item["task_id"] == air_task["task_id"] for item in evidence) == 8
        assert any(item["task_id"] is None and item["url"].startswith("/assets/") for item in evidence)
        analysis_tasks = client.get("/api/management/analysis-tasks", params={"project_id": project_id})
        assert analysis_tasks.status_code == 200
        air_analysis = next(item for item in analysis_tasks.json() if item["analysis_job_id"] == uploaded.json()["id"])
        assert air_analysis["video_file"] == video.name
        assert air_analysis["completed_count"] == 4
        assert air_analysis["total_stage_count"] == 4
        assert air_analysis["risk_count"] >= 0

        visualization = client.get(f"/api/management/analysis-jobs/{uploaded.json()['id']}/visualization")
        assert visualization.status_code == 200
        visual = visualization.json()
        assert visual["pipeline"] == ["upload", "frames", "detection", "result", "verification"]
        assert visual["task"]["analysis_job_id"] == uploaded.json()["id"]
        assert visual["task"]["video_url"].startswith("/uploads/")
        assert visual["task"]["original_video_url"].endswith(".mp4")
        assert visual["task"]["video_url"] == visual["task"]["original_video_url"]
        assert visual["task"]["video_preview_generated"] is False
        assert visual["summary"]["frame_count"] == 8
        assert visual["summary"]["boxed_frame_count"] >= 1
        assert any(
            detected.get("bbox_xyxy")
            for frame in visual["frames"]
            for detected in frame["detected_objects"]
            if isinstance(detected, dict)
        )
        assert all(frame["frame_url"].startswith("/uploads/") for frame in visual["frames"])
        assert all("frame_verdict" in frame for frame in visual["frames"])

        verification = client.get("/api/management/verification-workbench", params={"project_id": project_id})
        assert verification.status_code == 200
        air_verification = next(item for item in verification.json() if item["task_id"] == air_task["task_id"])
        assert air_verification["completed_count"] == 4
        assert air_verification["total_stage_count"] == 4
        assert air_verification["conclusion"] == "部分通过"
        objects = client.get("/api/management/engineering-objects").json()
        assert any(item["type"] == "光缆线路段" for item in objects)
        assert any(item["type"] == "光纤接续点" for item in objects)
        overview = client.get("/api/management/platform-overview", params={"project_id": project_id})
        assert overview.status_code == 200
        assert overview.json()["layers"]["analyzed_video_count"] == 1
        assert overview.json()["layers"]["object_count"] == len(objects)
        assert overview.json()["engines"]["safety_supervision"]["status"] in {"等待训练", "可运行"}
        assert overview.json()["engines"]["safety_supervision"]["result_count"] >= 0

        for path in (
            "/api/health", "/api/project", "/api/summary", "/api/objects",
            "/api/gis", "/api/rules", "/api/evidence", "/api/issues",
            "/api/exports/excel", "/api/exports/pdf", "/api/exports/archive",
        ):
            assert client.get(path).status_code == 200
        assert client.post("/api/admin/reset").status_code == 200


def test_unmatched_air_video_uses_task_analyzer_without_model_weights(tmp_path):
    source = Path("demo_air_blowing/input/BV1u2Mv6METn.mp4")
    changed_video = tmp_path / "uploaded_air_blowing.mp4"
    changed_video.write_bytes(source.read_bytes() + b"\0")

    with TestClient(app) as client:
        assert client.post("/api/admin/reset").status_code == 200
        dashboard = client.get("/api/management/dashboard").json()
        project_id = dashboard["project"]["project_id"]
        tasks = client.get("/api/management/tasks", params={"project_id": project_id}).json()
        air_task = next(task for task in tasks if task["task_type"] == "air_blowing")
        with changed_video.open("rb") as stream:
            uploaded = client.post(
                "/api/management/construction-data",
                data={"project_id": project_id, "task_id": air_task["task_id"]},
                files={"file": (changed_video.name, stream, "video/mp4")},
            )
        analyzed = client.get(f"/api/management/analysis-jobs/{uploaded.json()['id']}/visualization")
        assert analyzed.status_code == 200, analyzed.text
        assert analyzed.json()["summary"]["frame_count"] == 8
        detail = client.get(f"/api/ai/tasks/{air_task['task_id']}").json()
        assert {item["stage"] for item in detail["ai_analysis_results"]} == {
            "equipment_setup", "cable_loading", "blowing_process", "completion_check"
        }
        if model_status()["weights_available"]:
            assert any(item["detected_objects"] for item in detail["ai_analysis_results"])
        else:
            assert all(not item["detected_objects"] for item in detail["ai_analysis_results"])
        assert client.post("/api/admin/reset").status_code == 200


def test_geojson_collection_imports_real_engineering_object():
    payload = b'{"type":"FeatureCollection","features":[{"type":"Feature","properties":{"code":"TEST-CABLE-001","layer":"CABLE","object_type":"fiber_cable"},"geometry":{"type":"LineString","coordinates":[[104.0,30.0],[104.1,30.1]]}}]}'
    with TestClient(app) as client:
        assert client.post("/api/admin/reset").status_code == 200
        dashboard = client.get("/api/management/dashboard").json()
        project_id = dashboard["project"]["project_id"]
        task = client.get("/api/management/tasks", params={"project_id": project_id}).json()[0]
        uploaded = client.post(
            "/api/management/construction-data",
            data={"project_id": project_id, "task_id": task["task_id"]},
            files={"file": ("design.geojson", payload, "application/geo+json")},
        )
        assert uploaded.status_code == 200, uploaded.text
        assert uploaded.json()["data_type"] == "空间数据"
        assert uploaded.json()["gis_import"]["imported_count"] == 1
        objects = client.get("/api/management/engineering-objects").json()
        assert any(item["id"] == "TEST-CABLE-001" for item in objects)
        assert client.post("/api/admin/reset").status_code == 200
