from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any

from .database import db

EVIDENCE_LABELS = {
    "site_overview": "箱体整体及安装环境",
    "permanent_label": "永久编码与标识",
    "nap_internal_overview": "箱内整体布置",
    "nap_port": "NAP端口近景",
    "fiber_routing": "引下光纤独立路由",
    "cable_entry": "主缆/引入缆进缆口",
    "port_sequence": "端口排列及编号方向",
    "fiber_color_order": "芯线色序与端口对应",
    "splitter_installation": "分光器安装",
    "splice_protection": "熔接保护",
    "closure_sealing": "箱体密封与防护",
    "pre_acceptance_checklist": "预验收检查表",
    "acceptance_report": "验收测试报告",
    "otdr_report": "OTDR测试结果",
    "as_built_document": "竣工图及工程量文件",
}

REPORT_TYPES = {"acceptance_report", "otdr_report", "as_built_document"}
STATUS_ORDER = {"已验真": 3, "部分匹配": 2, "缺失影像": 1}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def infer_evidence_type(filename: str) -> tuple[str, str, float]:
    text = filename.lower()
    rules = [
        (("overview", "site", "outside", "全景", "整体"), "site_overview", 0.88),
        (("label", "code", "标识", "编码"), "permanent_label", 0.90),
        (("port", "nap", "端口"), "nap_port", 0.91),
        (("routing", "fiber", "光纤", "路由"), "fiber_routing", 0.86),
        (("internal", "inside", "箱内"), "nap_internal_overview", 0.85),
        (("otdr",), "otdr_report", 0.94),
        (("acceptance", "验收"), "acceptance_report", 0.92),
        (("asbuilt", "竣工"), "as_built_document", 0.92),
    ]
    for tokens, etype, score in rules:
        if any(token in text for token in tokens):
            return etype, EVIDENCE_LABELS[etype], score
    return "site_overview", EVIDENCE_LABELS["site_overview"], 0.58


def extract_code(text: str) -> str | None:
    patterns = [
        r"\b(?:PBO|BPE)-[A-Z]{3}-[A-Z]{3}-\d{4}\b",
        r"\b[A-Z]{3}-[A-Z]{3}-[A-Z]{3}-\d{4}\b",
    ]
    upper = text.upper().replace("_", "-")
    for pattern in patterns:
        m = re.search(pattern, upper)
        if m:
            return m.group(0)
    return None


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def candidate_matches(
    filename: str,
    detected_code: str | None,
    evidence_type: str,
    longitude: float | None = None,
    latitude: float | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    code = detected_code or extract_code(filename)
    with db() as conn:
        objects = [dict(r) for r in conn.execute("SELECT * FROM objects ORDER BY object_id").fetchall()]
    candidates: list[dict[str, Any]] = []
    for obj in objects:
        code_score = 0.0
        if code:
            if code == obj["object_id"]:
                code_score = 55.0
            elif code.split("-")[:3] == obj["object_id"].split("-")[:3]:
                code_score = 25.0
        type_score = 20.0 if obj["layer"] == "BOITE" and evidence_type in EVIDENCE_LABELS else 8.0
        location_score = 0.0
        distance = None
        if longitude is not None and latitude is not None and obj["longitude"] is not None and obj["latitude"] is not None:
            distance = haversine_m(longitude, latitude, obj["longitude"], obj["latitude"])
            if distance <= 30:
                location_score = 15.0
            elif distance <= 100:
                location_score = 10.0
            elif distance <= 300:
                location_score = 5.0
        context_score = 15.0 if obj["object_id"] in filename.upper().replace("_", "-") else 2.0
        time_score = 5.0
        total = min(100.0, code_score + type_score + location_score + context_score + time_score)
        reasons = []
        if code_score >= 55:
            reasons.append("工程编码完全一致 +55")
        elif code_score:
            reasons.append(f"编码前缀相符 +{code_score:.0f}")
        else:
            reasons.append("未获得对象级编码 +0")
        reasons.append(f"证据类型适用 +{type_score:.0f}")
        if distance is not None:
            reasons.append(f"空间距离 {distance:.0f}m +{location_score:.0f}")
        else:
            reasons.append("未提供定位信息 +0")
        reasons.append(f"文件上下文 +{context_score:.0f}")
        reasons.append(f"时间窗口可用 +{time_score:.0f}")
        candidates.append({
            "object_id": obj["object_id"],
            "object_type": obj["object_type"],
            "status": obj["status"],
            "score": round(total, 1),
            "distance_m": round(distance, 1) if distance is not None else None,
            "reasons": reasons,
            "components": {
                "code": code_score,
                "type": type_score,
                "location": location_score,
                "time": time_score,
                "context": context_score,
            },
        })
    return sorted(candidates, key=lambda x: (-x["score"], x["object_id"]))[:limit]


def recompute_object(object_id: str) -> dict[str, Any]:
    timestamp = now_iso()
    with db() as conn:
        mandatory = [dict(r) for r in conn.execute(
            "SELECT * FROM rules WHERE mandatory=1 ORDER BY sequence"
        ).fetchall()]
        evidence = [dict(r) for r in conn.execute(
            "SELECT * FROM evidence WHERE linked_object_id=? AND review_status='已确认'",
            (object_id,),
        ).fetchall()]
        present = {e["evidence_type"] for e in evidence}
        missing_rules = [r for r in mandatory if r["evidence_type"] not in present]
        matched_count = len(mandatory) - len(missing_rules)
        required_count = len(mandatory)
        completeness = matched_count / required_count if required_count else 1.0
        if completeness >= 0.999:
            status = "已验真"
            issue_type = "无"
        elif matched_count == 0:
            status = "缺失影像"
            issue_type = "影像缺失"
        else:
            status = "部分匹配"
            issue_type = "缺失证据"
        missing_text = "、".join(r["required_evidence"] for r in missing_rules) or "无"
        conn.execute(
            """INSERT INTO verification_results VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(object_id) DO UPDATE SET required_count=excluded.required_count,
               matched_count=excluded.matched_count, missing_evidence=excluded.missing_evidence,
               completeness=excluded.completeness, status=excluded.status,
               issue_type=excluded.issue_type, updated_at=excluded.updated_at""",
            (object_id, required_count, matched_count, missing_text, completeness, status, issue_type, timestamp),
        )
        conn.execute("UPDATE objects SET status=?, updated_at=? WHERE object_id=?", (status, timestamp, object_id))
    sync_issues_for_object(object_id)
    return {
        "object_id": object_id,
        "required_count": required_count,
        "matched_count": matched_count,
        "missing_evidence": missing_text,
        "completeness": completeness,
        "status": status,
        "issue_type": issue_type,
        "updated_at": timestamp,
    }


def _upsert_issue(conn, *, fingerprint: str, issue_type: str, severity: str, object_id: str | None,
                  evidence_id: str | None, rule_id: str | None, title: str, description: str, source: str) -> None:
    now = now_iso()
    existing = conn.execute("SELECT issue_id,status FROM issues WHERE fingerprint=?", (fingerprint,)).fetchone()
    if existing:
        next_status = existing["status"] if existing["status"] not in {"已关闭"} else "新发现"
        conn.execute(
            """UPDATE issues SET issue_type=?,severity=?,object_id=?,evidence_id=?,rule_id=?,title=?,description=?,
               source=?,status=?,updated_at=? WHERE fingerprint=?""",
            (issue_type,severity,object_id,evidence_id,rule_id,title,description,source,next_status,now,fingerprint),
        )
        return
    seq = conn.execute("SELECT COALESCE(MAX(CAST(SUBSTR(issue_id,5) AS INTEGER)),0) AS n FROM issues").fetchone()["n"] + 1
    conn.execute(
        """INSERT INTO issues(issue_id,issue_type,severity,object_id,evidence_id,rule_id,title,description,
           source,status,assignee,due_date,created_at,updated_at,resolution_note,fingerprint)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (f"ISS-{seq:04d}",issue_type,severity,object_id,evidence_id,rule_id,title,description,source,"新发现",None,None,now,now,None,fingerprint)
    )


def record_safety_issue(conn, *, task_id: str, evidence_id: str, object_id: str | None,
                        timestamp: float, risk: dict) -> None:
    if risk.get("risk") != "safety_helmet_missing":
        return
    confidence = float(risk.get("confidence") or 0)
    _upsert_issue(
        conn,
        fingerprint=f"{task_id}|安全帽违规",
        issue_type="安全违规",
        severity="高",
        object_id=object_id,
        evidence_id=evidence_id,
        rule_id=None,
        title="检测到未佩戴安全帽",
        description=f"施工影像 {timestamp:.1f} 秒处明确检测到未佩戴安全帽，检测分数 {confidence:.2f}，需人工复核。",
        source="安全视觉检测",
    )


def sync_issues_for_object(object_id: str) -> None:
    with db() as conn:
        result = dict(conn.execute("SELECT * FROM verification_results WHERE object_id=?", (object_id,)).fetchone())
        mandatory = [dict(r) for r in conn.execute("SELECT * FROM rules WHERE mandatory=1 ORDER BY sequence").fetchall()]
        evidence = [dict(r) for r in conn.execute("SELECT * FROM evidence WHERE linked_object_id=?", (object_id,)).fetchall()]
        confirmed = {e["evidence_type"] for e in evidence if e["review_status"] == "已确认"}
        active_fingerprints: set[str] = set()
        if result["matched_count"] == 0:
            fp = f"{object_id}|影像缺失"
            active_fingerprints.add(fp)
            _upsert_issue(conn, fingerprint=fp, issue_type="影像缺失", severity="高", object_id=object_id,
                          evidence_id=None, rule_id=None, title="对象未形成有效影像证据链",
                          description="当前对象没有任何已确认的强制影像证据。", source="规则引擎")
        missing_rules = [rule for rule in mandatory if rule["evidence_type"] not in confirmed]
        if missing_rules:
            fp = f"{object_id}|工序缺失"
            active_fingerprints.add(fp)
            severity = "高" if any(rule["sequence"] <= 3 for rule in missing_rules) else "中"
            missing_summary = "；".join(
                f"{rule['rule_id']} {rule['stage']}：{rule['required_evidence']}" for rule in missing_rules
            )
            _upsert_issue(
                conn, fingerprint=fp, issue_type="工序缺失", severity=severity, object_id=object_id,
                evidence_id=None, rule_id=missing_rules[0]["rule_id"],
                title=f"缺少{len(missing_rules)}项强制工序证据",
                description=missing_summary, source="验真规则"
            )
        if result["completeness"] < 1:
            fp = f"{object_id}|完整率不足"
            active_fingerprints.add(fp)
            _upsert_issue(conn, fingerprint=fp, issue_type="完整率不足",
                          severity="高" if result["completeness"] < 0.5 else "中", object_id=object_id,
                          evidence_id=None, rule_id=None, title="对象交付完整率未达标",
                          description=f"当前完整率为 {result['completeness']:.0%}，目标为 100%。", source="规则引擎")
        present_all = {e["evidence_type"] for e in evidence if e["review_status"] == "已确认"}
        missing_reports = sorted(REPORT_TYPES - present_all)
        if missing_reports:
            fp = f"{object_id}|缺少测试/报告"
            active_fingerprints.add(fp)
            report_labels = "、".join(EVIDENCE_LABELS[item] for item in missing_reports)
            _upsert_issue(conn, fingerprint=fp, issue_type="缺少测试/报告", severity="低", object_id=object_id,
                          evidence_id=None, rule_id=None, title=f"缺少{len(missing_reports)}项测试/交付资料",
                          description=f"待归档：{report_labels}。该类资料不计入首版5项强制完整率。", source="档案检查")
        # Close auto issues that no longer apply.
        rows = conn.execute("SELECT fingerprint,status FROM issues WHERE object_id=? AND source IN ('规则引擎','验真规则','档案检查')", (object_id,)).fetchall()
        for row in rows:
            if row["fingerprint"] not in active_fingerprints and row["status"] != "已关闭":
                conn.execute("UPDATE issues SET status='已关闭',resolution_note='系统复验通过',updated_at=? WHERE fingerprint=?", (now_iso(),row["fingerprint"]))


def sync_evidence_issues() -> None:
    with db() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM evidence").fetchall()]
        object_ids = {r["object_id"] for r in conn.execute("SELECT object_id FROM objects").fetchall()}
        for e in rows:
            active_fingerprints: set[str] = set()
            if not e["linked_object_id"] or e["linked_object_id"] not in object_ids:
                fp = f"{e['evidence_id']}|对象未关联"
                active_fingerprints.add(fp)
                _upsert_issue(conn, fingerprint=fp, issue_type="对象未关联", severity="高",
                              object_id=None, evidence_id=e["evidence_id"], rule_id=None, title="影像证据尚未关联工程对象",
                              description=f"文件 {e['filename']} 需要完成候选匹配和人工确认。", source="证据解析")
            detected = (e.get("detected_code") or "").strip()
            extracted_object_code = extract_code(detected) or extract_code(e.get("filename") or "")
            linked_is_valid = bool(e.get("linked_object_id") and e["linked_object_id"] in object_ids)
            review_confirmed = e.get("review_status") == "已确认"

            # 编码问题只在两种情况下保持打开：
            # 1) 证据尚未完成人工确认且没有稳定编码；
            # 2) 已识别出标准对象编码，但与已关联对象发生明确冲突。
            # 人工已确认的无编码照片不再重复制造“编码未匹配”噪声，
            # 其人工确认过程已由 match_method / verified_by / match_reason 留痕。
            pending_without_code = (
                not review_confirmed
                and (not detected or detected in {"未识别", "待复核"} or "待复核" in detected)
            )
            explicit_conflict = bool(
                linked_is_valid
                and extracted_object_code
                and extracted_object_code != e["linked_object_id"]
            )
            if pending_without_code or explicit_conflict:
                fp = f"{e['evidence_id']}|编码未匹配"
                active_fingerprints.add(fp)
                if explicit_conflict:
                    title = "识别编码与关联对象不一致"
                    description = (
                        f"文件 {e['filename']} 识别编码为 {extracted_object_code}，"
                        f"当前关联对象为 {e['linked_object_id']}，需要复核。"
                    )
                    severity = "高"
                else:
                    title = "影像编码识别结果需要复核"
                    description = f"文件 {e['filename']} 尚未获得稳定工程编码，且关联尚未确认。"
                    severity = "中"
                _upsert_issue(conn, fingerprint=fp, issue_type="编码未匹配", severity=severity,
                              object_id=e["linked_object_id"], evidence_id=e["evidence_id"], rule_id=None,
                              title=title, description=description, source="证据解析")
            existing = conn.execute(
                "SELECT fingerprint,status FROM issues WHERE evidence_id=? AND source='证据解析'",
                (e["evidence_id"],),
            ).fetchall()
            for issue in existing:
                if issue["fingerprint"] not in active_fingerprints and issue["status"] != "已关闭":
                    conn.execute(
                        "UPDATE issues SET status='已关闭',resolution_note='证据关联或编码复核完成',updated_at=? WHERE fingerprint=?",
                        (now_iso(), issue["fingerprint"]),
                    )


def synchronize_all() -> None:
    with db() as conn:
        object_ids = [r["object_id"] for r in conn.execute("SELECT object_id FROM objects ORDER BY object_id").fetchall()]
    for oid in object_ids:
        recompute_object(oid)
    sync_evidence_issues()
