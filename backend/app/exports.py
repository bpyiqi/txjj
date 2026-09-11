from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import xlsxwriter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .database import BASE_DIR, db
from .engine import now_iso


def _font_name() -> str:
    """Select a portable Chinese font without shipping font files."""
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        return "STSong-Light"
    except Exception:
        candidates = [
            Path("/usr/share/fonts/truetype/arphic-gbsn00lp/gbsn00lp.ttf"),
            Path("/usr/share/fonts/truetype/arphic-gkai00mp/gkai00mp.ttf"),
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ]
        for path in candidates:
            if path.exists():
                try:
                    pdfmetrics.registerFont(TTFont("CNFont", str(path)))
                    return "CNFont"
                except Exception:
                    continue
    return "Helvetica"


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _load_export_data() -> dict[str, Any]:
    with db() as conn:
        project = dict(conn.execute("SELECT * FROM project LIMIT 1").fetchone())
        objects = [dict(r) for r in conn.execute("SELECT * FROM objects ORDER BY object_id").fetchall()]
        results = {r["object_id"]: dict(r) for r in conn.execute("SELECT * FROM verification_results").fetchall()}
        evidence = [dict(r) for r in conn.execute("SELECT * FROM evidence ORDER BY evidence_id").fetchall()]
        rules = [dict(r) for r in conn.execute("SELECT * FROM rules ORDER BY sequence").fetchall()]
        issues = [dict(r) for r in conn.execute(
            """SELECT * FROM issues
               ORDER BY CASE severity WHEN '高' THEN 1 WHEN '中' THEN 2 ELSE 3 END,
                        CASE status WHEN '新发现' THEN 1 WHEN '待确认' THEN 2 WHEN '待整改' THEN 3 WHEN '已补证' THEN 4 ELSE 5 END,
                        issue_id"""
        ).fetchall()]
        status_rows = [dict(r) for r in conn.execute("SELECT status, COUNT(*) value FROM objects GROUP BY status").fetchall()]
        issue_rows = [dict(r) for r in conn.execute(
            "SELECT issue_type, COUNT(*) value FROM issues WHERE status!='已关闭' GROUP BY issue_type ORDER BY value DESC"
        ).fetchall()]
        avg_completeness = conn.execute("SELECT AVG(completeness) avg FROM verification_results").fetchone()["avg"] or 0
        open_issues = conn.execute("SELECT COUNT(*) n FROM issues WHERE status!='已关闭'").fetchone()["n"]
    return {
        "project": project,
        "objects": objects,
        "results": results,
        "evidence": evidence,
        "rules": rules,
        "issues": issues,
        "status_rows": status_rows,
        "issue_rows": issue_rows,
        "avg_completeness": avg_completeness,
        "open_issues": open_issues,
    }


def build_excel() -> bytes:
    data = _load_export_data()
    project = data["project"]
    objects = data["objects"]
    results = data["results"]
    evidence = data["evidence"]
    rules = data["rules"]
    issues = data["issues"]

    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True})
    workbook.set_properties({
        "title": f"{project['name']}数字化验真数据",
        "subject": "通信基建施工对象级验真与数字交付",
        "company": "通信基建施工透明化管理系统",
        "comments": "由施工数字化验真系统自动生成",
    })

    # Unified enterprise visual system.
    title_fmt = workbook.add_format({
        "bold": True, "font_size": 20, "font_color": "#16324F",
        "align": "left", "valign": "vcenter"
    })
    subtitle_fmt = workbook.add_format({"font_size": 10, "font_color": "#66788A", "valign": "vcenter"})
    section_fmt = workbook.add_format({
        "bold": True, "font_size": 12, "font_color": "#16324F",
        "bg_color": "#EAF0F5", "left": 4, "left_color": "#2F78A8", "valign": "vcenter"
    })
    label_fmt = workbook.add_format({"font_color": "#66788A", "bg_color": "#F6F8FA", "border": 1, "border_color": "#E0E7ED", "valign": "vcenter"})
    value_fmt = workbook.add_format({"bold": True, "font_color": "#23384B", "border": 1, "border_color": "#E0E7ED", "valign": "vcenter"})
    kpi_label = workbook.add_format({"font_size": 9, "font_color": "#66788A", "bg_color": "#F4F8FB", "align": "center", "valign": "vcenter", "top": 1, "left": 1, "right": 1, "border_color": "#DCE5EC"})
    kpi_value = workbook.add_format({"bold": True, "font_size": 18, "font_color": "#16324F", "bg_color": "#F4F8FB", "align": "center", "valign": "vcenter", "bottom": 1, "left": 1, "right": 1, "border_color": "#DCE5EC"})
    header = workbook.add_format({
        "bold": True, "font_color": "#FFFFFF", "bg_color": "#16324F",
        "border": 1, "border_color": "#16324F", "align": "center", "valign": "vcenter"
    })
    text = workbook.add_format({"font_color": "#263746", "border": 1, "border_color": "#E5EAF0", "valign": "top"})
    text_wrap = workbook.add_format({"font_color": "#263746", "border": 1, "border_color": "#E5EAF0", "valign": "top", "text_wrap": True})
    center = workbook.add_format({"font_color": "#263746", "border": 1, "border_color": "#E5EAF0", "align": "center", "valign": "vcenter"})
    pct = workbook.add_format({"num_format": "0%", "border": 1, "border_color": "#E5EAF0", "align": "center", "valign": "vcenter"})
    score_pct = workbook.add_format({"num_format": "0%", "border": 1, "border_color": "#E5EAF0", "align": "center", "valign": "vcenter"})
    dt_fmt = workbook.add_format({"num_format": "yyyy-mm-dd hh:mm", "font_color": "#425466", "border": 1, "border_color": "#E5EAF0", "align": "center", "valign": "vcenter"})
    status_formats = {
        "已验真": workbook.add_format({"bg_color": "#E7F6EF", "font_color": "#18794E", "border": 1, "border_color": "#D6E9DF", "align": "center", "valign": "vcenter"}),
        "部分匹配": workbook.add_format({"bg_color": "#FFF4E5", "font_color": "#B45B09", "border": 1, "border_color": "#F3DFC2", "align": "center", "valign": "vcenter"}),
        "缺失影像": workbook.add_format({"bg_color": "#FDECEC", "font_color": "#B42318", "border": 1, "border_color": "#F3D3D0", "align": "center", "valign": "vcenter"}),
        "已确认": workbook.add_format({"bg_color": "#E7F6EF", "font_color": "#18794E", "border": 1, "border_color": "#D6E9DF", "align": "center", "valign": "vcenter"}),
        "待确认": workbook.add_format({"bg_color": "#EEF2F5", "font_color": "#4A6072", "border": 1, "border_color": "#DDE4EA", "align": "center", "valign": "vcenter"}),
        "新发现": workbook.add_format({"bg_color": "#FDECEC", "font_color": "#B42318", "border": 1, "border_color": "#F3D3D0", "align": "center", "valign": "vcenter"}),
        "待整改": workbook.add_format({"bg_color": "#FFF4E5", "font_color": "#B45B09", "border": 1, "border_color": "#F3DFC2", "align": "center", "valign": "vcenter"}),
        "已补证": workbook.add_format({"bg_color": "#EAF3FA", "font_color": "#266A96", "border": 1, "border_color": "#D7E5EF", "align": "center", "valign": "vcenter"}),
        "已关闭": workbook.add_format({"bg_color": "#E7F6EF", "font_color": "#18794E", "border": 1, "border_color": "#D6E9DF", "align": "center", "valign": "vcenter"}),
    }
    severity_formats = {
        "高": workbook.add_format({"bg_color": "#FDECEC", "font_color": "#B42318", "bold": True, "border": 1, "border_color": "#F3D3D0", "align": "center"}),
        "中": workbook.add_format({"bg_color": "#FFF4E5", "font_color": "#B45B09", "bold": True, "border": 1, "border_color": "#F3DFC2", "align": "center"}),
        "低": workbook.add_format({"bg_color": "#EEF2F5", "font_color": "#52697B", "border": 1, "border_color": "#DDE4EA", "align": "center"}),
    }

    # Project overview sheet.
    ws = workbook.add_worksheet("项目概览")
    ws.hide_gridlines(2)
    ws.set_zoom(95)
    ws.set_column("A:A", 3)
    ws.set_column("B:I", 15)
    ws.set_column("J:J", 3)
    ws.set_row(0, 34)
    ws.merge_range("B1:I1", f"{project['name']} - 数字化验真交付数据", title_fmt)
    ws.merge_range("B2:I2", f"场景：{project['scenario']}  |  区域：{project.get('location') or '-'}  |  数据版本：{project.get('data_version') or '-'}", subtitle_fmt)

    status_map = {row["status"]: row["value"] for row in data["status_rows"]}
    kpis = [
        ("工程对象", len(objects)),
        ("影像证据", len(evidence)),
        ("已验真", status_map.get("已验真", 0)),
        ("部分匹配", status_map.get("部分匹配", 0)),
        ("缺失影像", status_map.get("缺失影像", 0)),
        ("待处理问题", data["open_issues"]),
        ("档案完整率", data["avg_completeness"]),
        ("强制规则", sum(1 for r in rules if r.get("mandatory"))),
    ]
    for idx, (label, value) in enumerate(kpis):
        col = 1 + idx
        ws.write(3, col, label, kpi_label)
        if label == "档案完整率":
            ws.write_number(4, col, value, workbook.add_format({**kpi_value.properties, "num_format": "0.0%"}) if hasattr(kpi_value, "properties") else kpi_value)
            ws.set_column(col, col, 15)
        else:
            ws.write(4, col, value, kpi_value)
    # Explicit percentage format fallback because XlsxWriter formats are immutable.
    ws.write_number(4, 7, data["avg_completeness"], workbook.add_format({"bold": True, "font_size": 18, "font_color": "#16324F", "bg_color": "#F4F8FB", "align": "center", "valign": "vcenter", "bottom": 1, "left": 1, "right": 1, "border_color": "#DCE5EC", "num_format": "0.0%"}))

    ws.merge_range("B7:I7", "项目与交付口径", section_fmt)
    metadata = [
        ("项目编号", project.get("project_id")),
        ("业务主线", " → ".join(json.loads(project.get("workflow_json") or "[]"))),
        ("生成时间", _parse_iso(now_iso())),
        ("完整率口径", "按首版5项强制施工影像验真节点计算"),
    ]
    for row_idx, (label, value) in enumerate(metadata, start=7):
        ws.write(row_idx, 1, label, label_fmt)
        if isinstance(value, datetime):
            ws.merge_range(row_idx, 2, row_idx, 8, value, dt_fmt)
        else:
            ws.merge_range(row_idx, 2, row_idx, 8, value or "-", value_fmt)
    ws.set_row(8, 30)

    ws.merge_range("B13:E13", "对象状态分布", section_fmt)
    ws.merge_range("F13:I13", "未关闭问题结构", section_fmt)
    for i, name in enumerate(["已验真", "部分匹配", "缺失影像"], start=13):
        ws.write(i, 1, name, label_fmt)
        ws.write(i, 2, status_map.get(name, 0), value_fmt)
    for i, row in enumerate(data["issue_rows"][:7], start=13):
        ws.write(i, 5, row["issue_type"], label_fmt)
        ws.write(i, 6, row["value"], value_fmt)
    ws.set_row(12, 24)
    ws.freeze_panes(3, 1)

    # Object ledger.
    ws = workbook.add_worksheet("对象验真台账")
    ws.hide_gridlines(2)
    ws.set_zoom(90)
    cols = ["对象编码", "图层", "类型", "所属SITE", "完整率", "必需节点", "已匹配节点", "缺失证据", "状态", "未关闭问题", "更新时间"]
    ws.write_row(0, 0, cols, header)
    for i, obj in enumerate(objects, 1):
        r = results[obj["object_id"]]
        issue_count = sum(1 for issue in issues if issue.get("object_id") == obj["object_id"] and issue.get("status") != "已关闭")
        values = [obj["object_id"], obj["layer"], obj["object_type"], obj["site_id"], r["completeness"], r["required_count"], r["matched_count"], r["missing_evidence"], r["status"], issue_count, _parse_iso(r["updated_at"])]
        for j, value in enumerate(values):
            if j == 4:
                fmt = pct
            elif j == 7:
                fmt = text_wrap
            elif j == 8:
                fmt = status_formats.get(value, center)
            elif j in {5, 6, 9}:
                fmt = center
            elif j == 10 and isinstance(value, datetime):
                fmt = dt_fmt
            else:
                fmt = text
            ws.write(i, j, value, fmt)
        ws.set_row(i, 34 if r["missing_evidence"] != "无" else 24)
    ws.freeze_panes(1, 1)
    ws.autofilter(0, 0, len(objects), len(cols) - 1)
    ws.set_row(0, 28)
    ws.set_column(0, 0, 24)
    ws.set_column(1, 3, 14)
    ws.set_column(4, 6, 12)
    ws.set_column(7, 7, 52)
    ws.set_column(8, 9, 14)
    ws.set_column(10, 10, 19)
    ws.conditional_format(1, 4, len(objects), 4, {"type": "data_bar", "bar_color": "#2AA876", "bar_solid": True})

    def make_sheet(name: str, columns: list[dict[str, Any]], rows: list[dict[str, Any]]) -> None:
        sheet = workbook.add_worksheet(name)
        sheet.hide_gridlines(2)
        sheet.set_zoom(90)
        sheet.write_row(0, 0, [c["label"] for c in columns], header)
        sheet.set_row(0, 28)
        for row_index, row in enumerate(rows, 1):
            max_height = 24
            for col_index, column in enumerate(columns):
                value = row.get(column["key"])
                transform = column.get("transform")
                if transform:
                    value = transform(value, row)
                fmt_name = column.get("format", "text")
                if fmt_name == "pct":
                    fmt = score_pct
                elif fmt_name == "date":
                    value = _parse_iso(value) if isinstance(value, str) else value
                    fmt = dt_fmt if isinstance(value, datetime) else center
                elif fmt_name == "center":
                    fmt = center
                elif fmt_name == "wrap":
                    fmt = text_wrap
                    max_height = max(max_height, 36)
                elif fmt_name == "status":
                    fmt = status_formats.get(value, center)
                elif fmt_name == "severity":
                    fmt = severity_formats.get(value, center)
                else:
                    fmt = text
                sheet.write(row_index, col_index, value, fmt)
            sheet.set_row(row_index, max_height)
        sheet.freeze_panes(1, 1)
        sheet.autofilter(0, 0, max(len(rows), 1), len(columns) - 1)
        for index, column in enumerate(columns):
            sheet.set_column(index, index, column.get("width", 16))

    make_sheet("影像证据", [
        {"key": "evidence_id", "label": "证据编号", "width": 12},
        {"key": "filename", "label": "文件名", "width": 32},
        {"key": "media_type", "label": "媒体类型", "width": 12, "format": "center"},
        {"key": "source_type", "label": "影像来源", "width": 14},
        {"key": "detected_code", "label": "识别编码", "width": 26},
        {"key": "linked_object_id", "label": "关联对象", "width": 24},
        {"key": "evidence_label", "label": "证据类型", "width": 24},
        {"key": "confidence_score", "label": "置信度", "width": 12, "format": "pct"},
        {"key": "review_status", "label": "审核状态", "width": 14, "format": "status"},
        {"key": "verified_by", "label": "确认方式", "width": 14, "format": "center"},
        {"key": "ocr_text", "label": "文本/OCR样例", "width": 46, "format": "wrap"},
        {"key": "captured_at", "label": "采集时间", "width": 19, "format": "date"},
    ], evidence)

    make_sheet("验真规则", [
        {"key": "rule_id", "label": "规则编号", "width": 12},
        {"key": "object_type", "label": "对象类型", "width": 14},
        {"key": "stage", "label": "验收节点", "width": 18},
        {"key": "required_evidence", "label": "所需证据", "width": 36, "format": "wrap"},
        {"key": "evidence_label", "label": "证据类型", "width": 26},
        {"key": "source_doc", "label": "规则来源", "width": 50, "format": "wrap"},
        {"key": "mandatory", "label": "强制", "width": 10, "format": "center", "transform": lambda value, _: "是" if value else "否"},
        {"key": "sequence", "label": "顺序", "width": 10, "format": "center"},
        {"key": "check_mode", "label": "检查方式", "width": 18},
        {"key": "acceptance_logic", "label": "判定逻辑", "width": 48, "format": "wrap"},
    ], rules)

    make_sheet("问题清单", [
        {"key": "issue_id", "label": "问题编号", "width": 14},
        {"key": "issue_type", "label": "问题类型", "width": 18},
        {"key": "severity", "label": "严重程度", "width": 12, "format": "severity"},
        {"key": "object_id", "label": "工程对象", "width": 24},
        {"key": "evidence_id", "label": "关联证据", "width": 14},
        {"key": "rule_id", "label": "触发规则", "width": 12},
        {"key": "title", "label": "问题标题", "width": 32, "format": "wrap"},
        {"key": "description", "label": "问题说明", "width": 52, "format": "wrap"},
        {"key": "source", "label": "触发来源", "width": 16},
        {"key": "status", "label": "处置状态", "width": 14, "format": "status"},
        {"key": "assignee", "label": "责任人", "width": 14},
        {"key": "due_date", "label": "整改期限", "width": 14},
        {"key": "updated_at", "label": "更新时间", "width": 19, "format": "date"},
        {"key": "resolution_note", "label": "处置记录", "width": 40, "format": "wrap"},
    ], issues)

    workbook.close()
    return output.getvalue()


def build_pdf() -> bytes:
    data = _load_export_data()
    project = data["project"]
    font = _font_name()
    buffer = io.BytesIO()

    status_map = {row["status"]: row["value"] for row in data["status_rows"]}
    objects = data["objects"]
    results = data["results"]
    open_issues = [i for i in data["issues"] if i["status"] != "已关闭"]
    priority_issues = open_issues[:6]

    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=13 * mm,
        bottomMargin=14 * mm,
        title=f"{project['name']}数字化验真报告",
        author="通信基建施工透明化管理系统",
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "TitleCN", parent=styles["Title"], fontName=font, fontSize=18,
        leading=24, textColor=colors.HexColor("#16324F"), alignment=TA_CENTER,
    )
    subtitle = ParagraphStyle(
        "SubtitleCN", parent=styles["BodyText"], fontName=font, fontSize=8.5,
        leading=12, textColor=colors.HexColor("#66788A"), alignment=TA_CENTER,
    )
    body = ParagraphStyle(
        "BodyCN", parent=styles["BodyText"], fontName=font, fontSize=8.2,
        leading=11.5, textColor=colors.HexColor("#263746"),
    )
    small = ParagraphStyle("SmallCN", parent=body, fontSize=7.2, leading=9.5)
    heading = ParagraphStyle("HeadingCN", parent=body, fontSize=12, leading=16, textColor=colors.HexColor("#16324F"))

    story = [
        Paragraph(f"{project['name']} - 数字化验真报告", title),
        Paragraph(
            f"场景：{project['scenario']}　区域：{project.get('location') or '-'}　数据版本：{project.get('data_version') or '-'}",
            subtitle,
        ),
        Spacer(1, 4 * mm),
    ]
    kpi_data = [
        ["工程对象", "已验真", "部分匹配", "缺失影像", "档案完整率", "待处理问题"],
        [
            len(objects),
            status_map.get("已验真", 0),
            status_map.get("部分匹配", 0),
            status_map.get("缺失影像", 0),
            f"{data['avg_completeness']:.1%}",
            data["open_issues"],
        ],
    ]
    kpi = Table(kpi_data, colWidths=[38 * mm] * 6, rowHeights=[9 * mm, 11 * mm])
    kpi.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16324F")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9E2EA")),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F5F8FA")),
    ]))
    story += [
        kpi,
        Spacer(1, 2 * mm),
        Paragraph("说明：档案完整率按首版5项强制施工影像验真节点计算；测试报告与竣工资料作为数字交付缺口单独统计。", small),
        Spacer(1, 4 * mm),
        Paragraph("对象验真台账", heading),
        Spacer(1, 2 * mm),
    ]

    ledger_data = [["对象编码", "类型", "完整率", "节点", "状态", "缺失证据"]]
    for obj in objects:
        result = results[obj["object_id"]]
        ledger_data.append([
            obj["object_id"],
            obj["object_type"],
            f"{result['completeness']:.0%}",
            f"{result['matched_count']}/{result['required_count']}",
            result["status"],
            Paragraph(result["missing_evidence"], small),
        ])
    ledger_table = Table(
        ledger_data,
        colWidths=[42 * mm, 18 * mm, 18 * mm, 18 * mm, 22 * mm, 120 * mm],
        repeatRows=1,
    )
    ledger_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF0F5")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#16324F")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D9E2EA")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFBFC")]),
    ]))
    story.append(ledger_table)
    story += [Spacer(1, 5 * mm), Paragraph("高优先级问题", heading), Spacer(1, 2 * mm)]

    issue_data = [["编号", "类型", "等级", "对象", "问题", "状态"]]
    for row in priority_issues:
        issue_data.append([
            row["issue_id"], row["issue_type"], row["severity"], row["object_id"] or "-",
            Paragraph(row["title"], small), row["status"],
        ])
    issue_table = Table(
        issue_data,
        colWidths=[20 * mm, 26 * mm, 14 * mm, 42 * mm, 105 * mm, 22 * mm],
        repeatRows=1,
    )
    issue_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF0F5")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#16324F")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D9E2EA")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFBFC")]),
    ]))
    story.append(issue_table)

    generated = _parse_iso(now_iso()) or datetime.now()

    def footer(canvas, document) -> None:
        canvas.saveState()
        canvas.setFont(font, 7)
        canvas.setFillColor(colors.HexColor("#7A8B99"))
        canvas.drawString(14 * mm, 7 * mm, f"生成时间：{generated:%Y-%m-%d %H:%M}")
        canvas.drawRightString(landscape(A4)[0] - 14 * mm, 7 * mm, f"第 {document.page} 页")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def build_archive() -> bytes:
    excel = build_excel()
    pdf = build_pdf()
    output = io.BytesIO()
    data = _load_export_data()
    project = data["project"]
    objects = data["objects"]
    results = list(data["results"].values())
    evidence = data["evidence"]
    issues = data["issues"]
    rules = data["rules"]
    manifest = {
        "archive_standard": "通信基建数字化交付档案",
        "project": project,
        "generated_at": now_iso(),
        "object_count": len(objects),
        "evidence_count": len(evidence),
        "rule_count": len(rules),
        "issue_count": len(issues),
        "generated_files": [
            "reports/验真报告.pdf",
            "reports/验真数据.xlsx",
            "data/project.json",
            "data/objects.json",
            "data/rules.json",
            "data/verification_results.json",
            "data/evidence.json",
            "data/issues.json",
        ],
    }
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("reports/验真报告.pdf", pdf)
        zf.writestr("reports/验真数据.xlsx", excel)
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        zf.writestr("data/project.json", json.dumps(project, ensure_ascii=False, indent=2))
        zf.writestr("data/objects.json", json.dumps(objects, ensure_ascii=False, indent=2))
        zf.writestr("data/rules.json", json.dumps(rules, ensure_ascii=False, indent=2))
        zf.writestr("data/verification_results.json", json.dumps(results, ensure_ascii=False, indent=2))
        zf.writestr("data/evidence.json", json.dumps(evidence, ensure_ascii=False, indent=2))
        zf.writestr("data/issues.json", json.dumps(issues, ensure_ascii=False, indent=2))
        assets_dir = BASE_DIR / "assets"
        for item in evidence:
            rel = item.get("asset_path")
            if not rel:
                continue
            path = assets_dir / rel
            if path.exists():
                folder = item.get("linked_object_id") or "UNLINKED"
                zf.write(path, f"evidence/{folder}/{item['evidence_id']}_{Path(rel).name}")
    return output.getvalue()
