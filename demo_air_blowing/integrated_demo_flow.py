from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from backend.app.main import app


PROJECT_ID = "VB-AI-INTEGRATED-001"
TASKS = [
    {
        "task_id": "TASK-INTEGRATED-AIR",
        "project_id": PROJECT_ID,
        "task_type": "air_blowing",
        "name": "光缆气吹施工",
        "sequence": 1,
        "linked_object_id": "PBO-JAD-MAR-0008",
    },
    {
        "task_id": "TASK-INTEGRATED-HANDOVER",
        "project_id": PROJECT_ID,
        "task_type": "handover",
        "name": "工程交接",
        "sequence": 2,
    },
    {
        "task_id": "TASK-INTEGRATED-SPLICE",
        "project_id": PROJECT_ID,
        "task_type": "fusion_splicing",
        "name": "光纤熔接施工",
        "sequence": 3,
        "linked_object_id": "PBO-JAD-MAR-0021",
    },
    {
        "task_id": "TASK-INTEGRATED-DELIVERY",
        "project_id": PROJECT_ID,
        "task_type": "digital_delivery",
        "name": "数字交付",
        "sequence": 4,
    },
]


def checked(response):
    assert response.status_code == 200, response.text
    return response


def run_flow(client: TestClient, write_outputs: bool = True) -> dict:
    checked(client.post("/api/admin/reset"))
    print("1/7 创建工程项目")
    project = checked(
        client.post(
            "/api/ai/projects",
            json={
                "project_id": PROJECT_ID,
                "name": "XX通信工程",
                "scenario": "高速公路通信工程光缆施工全过程智能验真",
                "location": "高速公路通信基础设施施工现场",
            },
        )
    ).json()

    print("2/7 创建并选择施工任务")
    for task in TASKS:
        checked(client.post("/api/ai/tasks", json=task))

    print("3/7 上传施工视频")
    videos = {
        "TASK-INTEGRATED-AIR": ROOT / "demo_air_blowing" / "input" / "BV1u2Mv6METn.mp4",
        "TASK-INTEGRATED-SPLICE": ROOT / "demo_air_blowing" / "input" / "BV1k5411P7qE.mp4",
    }
    for task_id, video_path in videos.items():
        with video_path.open("rb") as stream:
            checked(
                client.post(
                    f"/api/ai/tasks/{task_id}/upload-video",
                    files={"file": (video_path.name, stream, "video/mp4")},
                )
            )

    print("4/7 AI分析")
    analyzed = {}
    for task_id in videos:
        analyzed[task_id] = checked(client.post(f"/api/ai/tasks/{task_id}/analyze")).json()

    print("5/7 生成任务证据")
    evidence_count = sum(len(item["evidence"]) for item in analyzed.values())
    analysis_count = sum(len(item["ai_analysis_results"]) for item in analyzed.values())

    print("6/7 完成验真与工程交接")
    checked(client.post("/api/ai/tasks/TASK-INTEGRATED-AIR/complete"))
    checked(client.post("/api/ai/tasks/TASK-INTEGRATED-HANDOVER/complete"))
    checked(client.post("/api/ai/tasks/TASK-INTEGRATED-SPLICE/complete"))

    print("7/7 生成可信交付报告")
    delivery = checked(client.post(f"/api/ai/projects/{PROJECT_ID}/deliver")).json()
    report = checked(client.get(f"/api/ai/projects/{PROJECT_ID}/report.pdf"))
    dashboard = checked(client.get("/api/ai/dashboard", params={"project_id": PROJECT_ID})).json()
    result = {
        "project": project,
        "workflow": dashboard["workflow"],
        "evidence_count": evidence_count,
        "analysis_count": analysis_count,
        "risk_count": dashboard["summary"]["risk_count"],
        "delivery": delivery,
    }
    if write_outputs:
        output_dir = ROOT / "demo_air_blowing" / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "integrated_demo_result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        report_path = ROOT / "output" / "pdf" / "通信基建施工数字化验真交付报告.pdf"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_bytes(report.content)
        print(f"报告：{report_path}")
    return result


def main() -> None:
    with TestClient(app) as client:
        result = run_flow(client)
    print(
        f"完成：{result['evidence_count']} 条证据，"
        f"{result['analysis_count']} 条AI结果，{result['risk_count']} 项风险/补证。"
    )


if __name__ == "__main__":
    main()
