from fastapi.testclient import TestClient

from backend.app.database import db
from backend.app.main import app
from demo_air_blowing.integrated_demo_flow import PROJECT_ID, run_flow


def test_integrated_ai_construction_workflow():
    with TestClient(app) as client:
        result = run_flow(client, write_outputs=False)
        assert result["project"]["project_id"] == PROJECT_ID
        assert result["evidence_count"] == 17
        assert result["analysis_count"] == 17
        assert result["risk_count"] >= 1
        assert [item["status"] for item in result["workflow"]] == ["完成", "完成", "完成", "生成"]

        air = client.get("/api/ai/tasks/TASK-INTEGRATED-AIR").json()
        splice = client.get("/api/ai/tasks/TASK-INTEGRATED-SPLICE").json()
        assert len(air["evidence"]) == 8
        assert len(splice["evidence"]) == 9
        assert all(item["task_id"] == "TASK-INTEGRATED-AIR" for item in air["ai_analysis_results"])
        assert all(item["task_id"] == "TASK-INTEGRATED-SPLICE" for item in splice["ai_analysis_results"])
        assert any("bbox_xyxy" in obj for item in air["ai_analysis_results"] for obj in item["detected_objects"])
        assert any("bbox_xyxy" in obj for item in splice["ai_analysis_results"] for obj in item["detected_objects"])
        assert {item["acceptance_rule"]["detected_scene"] for item in air["ai_analysis_results"]} == {"air_blowing"}
        assert {item["acceptance_rule"]["detected_scene"] for item in splice["ai_analysis_results"]} == {"fusion_splicing"}
        yolo = client.get("/api/ai/yolo/status")
        safety = client.get("/api/ai/safety/status")
        assert yolo.status_code == 200
        assert safety.status_code == 200
        assert yolo.json()["weights_available"] is True
        assert client.get(f"/api/ai/projects/{PROJECT_ID}/report.pdf").content.startswith(b"%PDF")

        for legacy_path in (
            "/api/health", "/api/project", "/api/summary", "/api/objects",
            "/api/gis", "/api/rules", "/api/evidence", "/api/issues",
            "/api/exports/excel", "/api/exports/pdf", "/api/exports/archive",
        ):
            assert client.get(legacy_path).status_code == 200

        with db() as conn:
            assert conn.execute("SELECT COUNT(*) n FROM construction_tasks WHERE project_id=?", (PROJECT_ID,)).fetchone()["n"] == 4
            assert conn.execute("SELECT COUNT(*) n FROM construction_task_evidence te JOIN evidence e ON e.evidence_id=te.evidence_id JOIN ai_analysis_results ar ON ar.evidence_id=e.evidence_id WHERE te.task_id=ar.task_id").fetchone()["n"] >= 17
        assert client.post("/api/admin/reset").status_code == 200
