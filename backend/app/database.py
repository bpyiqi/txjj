from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "verification.db"
SEED_PATH = DATA_DIR / "seed.json"


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS project (
            project_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            scenario TEXT NOT NULL,
            location TEXT,
            data_version TEXT,
            updated_at TEXT,
            workflow_json TEXT NOT NULL,
            governance_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS objects (
            object_id TEXT PRIMARY KEY,
            layer TEXT NOT NULL,
            object_type TEXT NOT NULL,
            geometry_type TEXT NOT NULL,
            longitude REAL,
            latitude REAL,
            location TEXT,
            source_file TEXT,
            status TEXT NOT NULL,
            site_id TEXT,
            ptc_code TEXT,
            capacity INTEGER,
            mode_pose TEXT,
            structure_type TEXT,
            manufacturer TEXT,
            upstream_cable TEXT,
            city TEXT,
            attributes_json TEXT NOT NULL,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS gis_features (
            feature_id TEXT NOT NULL,
            layer TEXT NOT NULL,
            geometry_type TEXT NOT NULL,
            coordinates_json TEXT NOT NULL,
            status TEXT,
            properties_json TEXT NOT NULL,
            PRIMARY KEY(feature_id, layer)
        );

        CREATE TABLE IF NOT EXISTS rules (
            rule_id TEXT PRIMARY KEY,
            object_type TEXT NOT NULL,
            stage TEXT NOT NULL,
            required_evidence TEXT NOT NULL,
            evidence_type TEXT NOT NULL,
            evidence_label TEXT NOT NULL,
            source_doc TEXT NOT NULL,
            mandatory INTEGER NOT NULL,
            sequence INTEGER NOT NULL,
            check_mode TEXT,
            acceptance_logic TEXT
        );

        CREATE TABLE IF NOT EXISTS evidence (
            evidence_id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            media_type TEXT NOT NULL,
            source_type TEXT NOT NULL,
            detected_code TEXT,
            linked_object_id TEXT,
            evidence_type TEXT NOT NULL,
            evidence_label TEXT NOT NULL,
            confidence_label TEXT,
            confidence_score REAL,
            verified_by TEXT,
            review_status TEXT,
            match_method TEXT,
            match_reason TEXT,
            ocr_text TEXT,
            captured_at TEXT,
            asset_path TEXT,
            latitude REAL,
            longitude REAL,
            created_at TEXT,
            FOREIGN KEY(linked_object_id) REFERENCES objects(object_id)
        );

        CREATE TABLE IF NOT EXISTS verification_results (
            object_id TEXT PRIMARY KEY,
            required_count INTEGER NOT NULL,
            matched_count INTEGER NOT NULL,
            missing_evidence TEXT,
            completeness REAL NOT NULL,
            status TEXT NOT NULL,
            issue_type TEXT,
            updated_at TEXT,
            FOREIGN KEY(object_id) REFERENCES objects(object_id)
        );

        CREATE TABLE IF NOT EXISTS issues (
            issue_id TEXT PRIMARY KEY,
            issue_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            object_id TEXT,
            evidence_id TEXT,
            rule_id TEXT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            source TEXT NOT NULL,
            status TEXT NOT NULL,
            assignee TEXT,
            due_date TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            resolution_note TEXT,
            fingerprint TEXT UNIQUE,
            FOREIGN KEY(object_id) REFERENCES objects(object_id),
            FOREIGN KEY(evidence_id) REFERENCES evidence(evidence_id),
            FOREIGN KEY(rule_id) REFERENCES rules(rule_id)
        );

        CREATE TABLE IF NOT EXISTS activities (
            activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_type TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            object_id TEXT,
            evidence_id TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS construction_tasks (
            task_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            task_type TEXT NOT NULL,
            name TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            status TEXT NOT NULL,
            linked_object_id TEXT,
            source_video_path TEXT,
            source_video_sha256 TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES project(project_id),
            FOREIGN KEY(linked_object_id) REFERENCES objects(object_id)
        );

        CREATE TABLE IF NOT EXISTS construction_task_evidence (
            task_id TEXT NOT NULL,
            evidence_id TEXT NOT NULL,
            source_timestamp REAL,
            evidence_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(task_id, evidence_id),
            FOREIGN KEY(task_id) REFERENCES construction_tasks(task_id),
            FOREIGN KEY(evidence_id) REFERENCES evidence(evidence_id)
        );

        CREATE TABLE IF NOT EXISTS ai_analysis_results (
            analysis_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            evidence_id TEXT NOT NULL,
            stage TEXT NOT NULL,
            detected_objects_json TEXT NOT NULL,
            confidence REAL NOT NULL,
            risk_json TEXT NOT NULL,
            engineering_object_json TEXT NOT NULL,
            acceptance_rule_json TEXT NOT NULL,
            evidence_hash TEXT NOT NULL,
            model_name TEXT NOT NULL,
            model_version TEXT NOT NULL,
            review_status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(task_id) REFERENCES construction_tasks(task_id),
            FOREIGN KEY(evidence_id) REFERENCES evidence(evidence_id)
        );

        CREATE TABLE IF NOT EXISTS ai_delivery_reports (
            report_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            title TEXT NOT NULL,
            report_path TEXT,
            report_sha256 TEXT,
            status TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES project(project_id)
        );

        CREATE TABLE IF NOT EXISTS construction_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            data_type TEXT NOT NULL,
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            upload_time TEXT NOT NULL,
            status TEXT NOT NULL,
            progress INTEGER NOT NULL DEFAULT 0,
            stage_message TEXT,
            error_message TEXT,
            file_sha256 TEXT,
            started_at TEXT,
            completed_at TEXT,
            FOREIGN KEY(task_id) REFERENCES construction_tasks(task_id)
        );

        CREATE TABLE IF NOT EXISTS engineering_objects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            location TEXT,
            status TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS gis_import_meta (
            source_path TEXT PRIMARY KEY,
            source_sha256 TEXT NOT NULL,
            feature_count INTEGER NOT NULL,
            imported_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_construction_tasks_project
            ON construction_tasks(project_id, sequence);
        CREATE INDEX IF NOT EXISTS idx_task_evidence_task
            ON construction_task_evidence(task_id);
        CREATE INDEX IF NOT EXISTS idx_ai_results_task
            ON ai_analysis_results(task_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_construction_data_task
            ON construction_data(task_id, upload_time);
        """
    )
    # Lightweight migrations for databases created by earlier demo versions.
    construction_columns = {row["name"] for row in conn.execute("PRAGMA table_info(construction_data)")}
    for name, declaration in {
        "progress": "INTEGER NOT NULL DEFAULT 0",
        "stage_message": "TEXT",
        "error_message": "TEXT",
        "file_sha256": "TEXT",
        "started_at": "TEXT",
        "completed_at": "TEXT",
    }.items():
        if name not in construction_columns:
            conn.execute(f"ALTER TABLE construction_data ADD COLUMN {name} {declaration}")
    analysis_columns = {row["name"] for row in conn.execute("PRAGMA table_info(ai_analysis_results)")}
    if "data_id" not in analysis_columns:
        conn.execute("ALTER TABLE ai_analysis_results ADD COLUMN data_id INTEGER")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_results_data ON ai_analysis_results(data_id, created_at)")
    conn.execute(
        """UPDATE ai_analysis_results
           SET data_id=(SELECT MAX(d.id) FROM construction_data d
                        WHERE d.task_id=ai_analysis_results.task_id AND d.data_type='施工视频')
           WHERE data_id IS NULL"""
    )
    conn.execute(
        """UPDATE construction_data
           SET progress=100,
               stage_message=COALESCE(stage_message,'分析与验真完成'),
               completed_at=COALESCE(completed_at,upload_time)
           WHERE status='已分析' AND COALESCE(progress,0)<100"""
    )


def _seed_ai_demo_project(conn: sqlite3.Connection) -> None:
    """Add the integrated AI demo without changing the legacy seed rows."""
    now = "2026-09-07T09:00:00"
    project_id = "VB-AI-DEMO-001"
    conn.execute(
        """INSERT OR IGNORE INTO project
           (project_id,name,scenario,location,data_version,updated_at,workflow_json,governance_json)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            project_id,
            "XX通信工程",
            "高速公路通信工程光缆施工全过程智能验真",
            "高速公路通信基础设施施工现场",
            "通信基建施工数据集",
            now,
            json.dumps(
                ["光缆气吹施工", "工程交接", "光纤熔接施工", "数字交付"],
                ensure_ascii=False,
            ),
            json.dumps(
                {"evidence_hash": "SHA-256", "review": "AI分析+人工复核"},
                ensure_ascii=False,
            ),
        ),
    )
    tasks = [
        ("TASK-AIR-001", "air_blowing", "光缆气吹施工", 1, "完成", "PBO-JAD-MAR-0008"),
        ("TASK-HANDOVER-001", "handover", "工程交接", 2, "完成", None),
        ("TASK-SPLICE-001", "fusion_splicing", "光纤熔接施工", 3, "完成", "PBO-JAD-MAR-0021"),
        ("TASK-DELIVERY-001", "digital_delivery", "数字交付", 4, "待生成", None),
    ]
    for task_id, task_type, name, sequence, status, object_id in tasks:
        conn.execute(
            """INSERT OR IGNORE INTO construction_tasks
               (task_id,project_id,task_type,name,sequence,status,linked_object_id,
                source_video_path,source_video_sha256,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                task_id, project_id, task_type, name, sequence, status, object_id,
                None, None, now, now,
            ),
        )


def _sync_engineering_objects(conn: sqlite3.Connection) -> None:
    """Expose existing assets through the lightweight management ledger."""
    rows = conn.execute(
        "SELECT object_id,object_type,location,site_id,status FROM objects"
    ).fetchall()
    for row in rows:
        object_type = (
            "光缆线路段" if row["object_id"] == "PBO-JAD-MAR-0008"
            else "光纤接续点" if row["object_id"] == "PBO-JAD-MAR-0021"
            else row["object_type"]
        )
        conn.execute(
            """INSERT INTO engineering_objects(id,name,type,location,status)
               VALUES (?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET name=excluded.name,
               type=excluded.type,location=excluded.location,status=excluded.status""",
            (
                row["object_id"],
                object_type if object_type in {"光缆线路段", "光纤接续点"} else f"通信设施 {row['object_id']}",
                object_type,
                row["location"] or row["site_id"] or "施工现场",
                row["status"],
            ),
        )


def initialize_database(force: bool = False) -> None:
    if force and DB_PATH.exists():
        DB_PATH.unlink()
    with db() as conn:
        _create_schema(conn)
        exists = conn.execute("SELECT COUNT(*) AS n FROM project").fetchone()["n"]
        if exists:
            _seed_ai_demo_project(conn)
            _sync_engineering_objects(conn)
            return
        seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        p = seed["project"]
        conn.execute(
            "INSERT INTO project VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                p["project_id"], p["name"], p["scenario"], p.get("location"),
                p.get("data_version"), p.get("updated_at"),
                json.dumps(p.get("workflow", []), ensure_ascii=False),
                json.dumps(p.get("data_governance", {}), ensure_ascii=False),
            ),
        )
        for o in seed["objects"]:
            conn.execute(
                """INSERT INTO objects (
                    object_id,layer,object_type,geometry_type,longitude,latitude,location,source_file,status,
                    site_id,ptc_code,capacity,mode_pose,structure_type,manufacturer,upstream_cable,city,
                    attributes_json,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    o["object_id"],o["layer"],o["object_type"],o["geometry_type"],o.get("longitude"),o.get("latitude"),
                    o.get("location"),o.get("source_file"),o["status"],o.get("site_id"),o.get("ptc_code"),o.get("capacity"),
                    o.get("mode_pose"),o.get("structure_type"),o.get("manufacturer"),o.get("upstream_cable"),o.get("city"),
                    json.dumps(o.get("attributes",{}),ensure_ascii=False),o.get("updated_at")
                )
            )
        for layer, features in seed["gis_features"].items():
            for f in features:
                conn.execute(
                    "INSERT INTO gis_features VALUES (?,?,?,?,?,?)",
                    (f["feature_id"],f["layer"],f["geometry_type"],json.dumps(f["coordinates"],ensure_ascii=False),
                     f.get("status"),json.dumps(f.get("properties",{}),ensure_ascii=False))
                )
        for r in seed["rules"]:
            conn.execute(
                "INSERT INTO rules VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (r["rule_id"],r["object_type"],r["stage"],r["required_evidence"],r["evidence_type"],r["evidence_label"],
                 r["source_doc"],int(r["mandatory"]),r["sequence"],r.get("check_mode"),r.get("acceptance_logic"))
            )
        for e in seed["evidence"]:
            conn.execute(
                """INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (e["evidence_id"],e["filename"],e["media_type"],e["source_type"],e.get("detected_code"),
                 e.get("linked_object_id") or None,e["evidence_type"],e["evidence_label"],e.get("confidence_label"),
                 e.get("confidence_score"),e.get("verified_by"),e.get("review_status"),e.get("match_method"),e.get("match_reason"),
                 e.get("ocr_text"),e.get("captured_at"),e.get("asset_path"),e.get("latitude"),e.get("longitude"),e.get("created_at"))
            )
        for r in seed["results"]:
            conn.execute(
                "INSERT INTO verification_results VALUES (?,?,?,?,?,?,?,?)",
                (r["object_id"],r["required_count"],r["matched_count"],r.get("missing_evidence"),r["completeness"],
                 r["status"],r.get("issue_type"),r.get("updated_at"))
            )
        _seed_ai_demo_project(conn)
        _sync_engineering_objects(conn)


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None
