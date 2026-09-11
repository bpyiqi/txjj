from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo_air_blowing"
AIR_PATH = DEMO / "output" / "construction_evidence.json"
SPLICE_PATH = DEMO / "output" / "fiber_splicing_evidence.json"
SPLICE_METRICS_PATH = DEMO / "output" / "fiber_splicing_metrics.json"
SUMMARY_PATH = DEMO / "output" / "full_process_summary.json"
REPORT_MD_PATH = DEMO / "output" / "高速公路通信工程光缆施工全过程智能验真报告.md"
REPORT_PDF_PATH = ROOT / "output" / "pdf" / "高速公路通信工程光缆施工全过程智能验真报告.pdf"

AIR_STAGE_ZH = {
    "equipment_setup": "设备布设",
    "cable_loading": "光缆上料",
    "blowing_process": "气吹敷设",
    "completion_check": "完工检查",
}
SPLICE_STAGE_ZH = {
    "fiber_stripping": "光纤剥除",
    "fiber_cleaning": "光纤清洁",
    "fiber_cleaving": "光纤切割",
    "fusion_splicing": "光纤熔接",
    "fiber_organizing": "盘纤整理",
}
OBJECT_ZH = {
    "fusion_splicer": "熔接机",
    "fiber": "光纤",
    "splice_tray": "接续盘",
    "protection_sleeve": "热缩保护套管",
    "technician": "熔接技术人员",
}


def load() -> tuple[dict, list[dict], dict]:
    return (
        json.loads(AIR_PATH.read_text(encoding="utf-8")),
        json.loads(SPLICE_PATH.read_text(encoding="utf-8")),
        json.loads(SPLICE_METRICS_PATH.read_text(encoding="utf-8")),
    )


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def build_summary(air: dict, splice: list[dict], metrics: dict) -> dict:
    air_summary = air["summary"]
    correct = air_summary["correct_stage_count"] + metrics["correct_stage_count"]
    total = air_summary["sample_count"] + metrics["sample_count"]
    return {
        "system_name": "面向高速公路通信基础设施建设的光缆敷设施工智能监管与可信交付系统",
        "report_title": "高速公路通信工程光缆施工全过程智能验真报告",
        "process_scope": ["Air Blowing", "Fusion Splicing"],
        "video_count": air_summary["video_count"] + 1,
        "evidence_count": total,
        "stage_count": len(AIR_STAGE_ZH) + len(SPLICE_STAGE_ZH),
        "correct_stage_count": correct,
        "combined_stage_accuracy": round(correct / total, 4),
        "air_blowing": {
            "sample_count": air_summary["sample_count"],
            "stage_accuracy": air_summary["stage_accuracy"],
            "video_count": air_summary["video_count"],
        },
        "fusion_splicing": {
            "sample_count": metrics["sample_count"],
            "stage_accuracy": metrics["stage_accuracy"],
            "video_count": 1,
            "covered_objects": metrics["covered_objects"],
            "missing_target_objects": metrics["missing_target_objects"],
        },
        "integrity": {
            "algorithm": "SHA-256",
            "air_blowing_frame_hashes": len(air["evidence"]),
            "fiber_splicing_evidence_hashes": len(splice),
        },
        "trust_boundary": "Demo 目标采用人工复核领域标注；工序由轻量规则推断。结果用于辅助监管，不替代法定验收。",
    }


def write_markdown(air: dict, splice: list[dict], metrics: dict, summary: dict) -> None:
    counts = Counter(item["stage"] for item in splice)
    lines = [
        "# 高速公路通信工程光缆施工全过程智能验真报告",
        "",
        "> 施工全过程：**Air Blowing + Fusion Splicing**",
        "",
        "## 1. 系统定位",
        "",
        "面向高速公路通信基础设施建设，对光缆气吹敷设与光纤熔接接续两类关键工序进行智能识别、证据固化、风险提示和可信归档。",
        "",
        "## 2. 全过程证据链",
        "",
        "```text",
        "Air Blowing",
        "设备布设 → 光缆上料 → 气吹敷设 → 完工检查",
        "                         ↓ 工程对象交接",
        "Fusion Splicing",
        "光纤剥除 → 光纤清洁 → 光纤切割 → 光纤熔接 → 盘纤整理",
        "```",
        "",
        "## 3. 总体验证结果",
        "",
        "| 指标 | 结果 |",
        "|---|---:|",
        f"| 视频数量 | {summary['video_count']} |",
        f"| 证据样本 | {summary['evidence_count']} |",
        f"| 工序类型 | {summary['stage_count']} |",
        f"| 工序预测正确 | {summary['correct_stage_count']}/{summary['evidence_count']} |",
        f"| 小样本综合准确率 | {pct(summary['combined_stage_accuracy'])} |",
        "",
        "综合准确率仅用于当前 3 段视频、25 个抽样证据的 Demo 验证，不代表生产部署精度。",
        "",
        "## 4. Air Blowing 验真",
        "",
        f"- 视频：2 段；证据：{air['summary']['sample_count']} 帧；工序准确率：{pct(air['summary']['stage_accuracy'])}。",
        "- 来源：[高速公路通信工程吹缆施工现场](https://www.bilibili.com/video/BV1u2Mv6METn/)；[硅芯管高速气吹光缆施工](https://www.bilibili.com/video/BV1Ld4y1X7AA/)。",
        "- 输出：`construction_evidence.json`，包含视频、时间戳、帧、目标、工序、工程对象、验收规则、风险与哈希。",
        "",
        "## 5. Fusion Splicing 验真",
        "",
        f"- 来源：[光纤熔接视频教程](https://www.bilibili.com/video/BV1k5411P7qE/)，时长约 175 秒。",
        f"- 证据：{metrics['sample_count']} 条；五类工序准确率：{pct(metrics['stage_accuracy'])}。",
        f"- 工序覆盖：{'、'.join(f'{SPLICE_STAGE_ZH[stage]} {counts[stage]} 条' for stage in SPLICE_STAGE_ZH)}。",
        f"- 目标覆盖：{'、'.join(OBJECT_ZH[item] for item in metrics['covered_objects'])}。",
        "- 接续盘 `splice_tray` 未在本视频中清晰出现，系统将其记录为补证项，不生成虚假检出。",
        "",
        "| 时间戳 | 阶段 | 检出目标 | 置信度 | 证据哈希前缀 |",
        "|---:|---|---|---:|---|",
    ]
    for item in splice:
        objects = "、".join(OBJECT_ZH[obj["label"]] for obj in item["detected_objects"])
        lines.append(
            f"| {item['timestamp']:.1f}s | {SPLICE_STAGE_ZH[item['stage']]} | {objects} | {item['confidence']:.2f} | `{item['evidence_hash'][:16]}…` |"
        )
    lines += [
        "",
        "## 6. 可信交付说明",
        "",
        "- Air Blowing 证据帧保存帧级 SHA-256；Fusion Splicing 以源视频 SHA-256、时间戳及规范化证据载荷生成证据哈希。",
        "- 目标检测置信度为 Demo 人工复核配置；新视频生产识别需训练通信施工领域 YOLO 权重。",
        "- 接续盘未出现、完工检查不充分、安全帽未确认等情况均进入人工复核或补证，不自动替代监理签认。",
        "",
        "## 7. 应用价值",
        "",
        "1. 串联敷设与接续工序，形成光缆施工全过程监管视图。",
        "2. 固化隐蔽工程影像、工序判断和证据哈希，支持责任追溯。",
        "3. 自动生成竣工数字档案，减少人工抽帧、分类和整理工作。",
    ]
    REPORT_MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def chinese_font() -> str:
    for path in (Path(r"C:\Windows\Fonts\msyh.ttc"), Path(r"C:\Windows\Fonts\simhei.ttf"), Path(r"C:\Windows\Fonts\simsun.ttc")):
        if path.exists():
            return str(path)
    raise FileNotFoundError("未找到中文字体")


def write_pdf(air: dict, splice: list[dict], metrics: dict, summary: dict) -> None:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    REPORT_PDF_PATH.parent.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(TTFont("CN", chinese_font()))
    navy, cyan, pale, gray = colors.HexColor("#17324D"), colors.HexColor("#00A6A6"), colors.HexColor("#EAF7F6"), colors.HexColor("#637487")
    styles = getSampleStyleSheet()
    title = ParagraphStyle("title", parent=styles["Title"], fontName="CN", fontSize=21, leading=29, textColor=navy, alignment=TA_CENTER, spaceAfter=8 * mm)
    subtitle = ParagraphStyle("subtitle", parent=styles["BodyText"], fontName="CN", fontSize=11, leading=18, textColor=gray, alignment=TA_CENTER)
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontName="CN", fontSize=15, leading=21, textColor=navy, spaceBefore=5 * mm, spaceAfter=3 * mm)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName="CN", fontSize=12, leading=17, textColor=cyan, spaceBefore=3 * mm, spaceAfter=2 * mm)
    body = ParagraphStyle("body", parent=styles["BodyText"], fontName="CN", fontSize=9.3, leading=15, textColor=colors.HexColor("#263746"))
    small = ParagraphStyle("small", parent=body, fontSize=7.4, leading=10.5, textColor=gray)
    metric = ParagraphStyle("metric", parent=body, fontSize=15, leading=19, textColor=navy, alignment=TA_CENTER)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D5E0E8"))
        canvas.line(18 * mm, 14 * mm, 192 * mm, 14 * mm)
        canvas.setFont("CN", 7)
        canvas.setFillColor(gray)
        canvas.drawString(18 * mm, 9 * mm, "通信光缆施工全过程智能验真")
        canvas.drawRightString(192 * mm, 9 * mm, f"第 {doc.page} 页")
        canvas.restoreState()

    def styled_table(rows, widths, header=True):
        table = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
        commands = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C8D6E0")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]
        if header:
            commands += [("BACKGROUND", (0, 0), (-1, 0), navy), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]
        table.setStyle(TableStyle(commands))
        return table

    doc = SimpleDocTemplate(str(REPORT_PDF_PATH), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=19 * mm, title=summary["report_title"], author="通信基建施工管理系统")
    story = [Spacer(1, 10 * mm), Paragraph("高速公路通信工程光缆施工全过程智能验真报告", title), Paragraph("Air Blowing + Fusion Splicing", ParagraphStyle("en", parent=subtitle, fontSize=15, textColor=cyan)), Spacer(1, 3 * mm), Paragraph("面向高速公路通信基础设施建设的光缆敷设施工智能监管与可信交付系统", subtitle), Spacer(1, 10 * mm)]
    process_rows = [
        [Paragraph("01", metric), Paragraph("Air Blowing", h2), Paragraph("设备布设 → 光缆上料 → 气吹敷设 → 完工检查", body)],
        [Paragraph("＋", metric), Paragraph("工程交接", h2), Paragraph("敷设完成、接续准备、证据链衔接", body)],
        [Paragraph("02", metric), Paragraph("Fusion Splicing", h2), Paragraph("光纤剥除 → 清洁 → 切割 → 熔接 → 盘纤整理", body)],
    ]
    process = Table(process_rows, colWidths=[22 * mm, 42 * mm, 94 * mm])
    process.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, -1), pale), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C8D6E0")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    story += [process, Spacer(1, 8 * mm)]
    stats = [[Paragraph(f"<b>{summary['video_count']}</b><br/><font size=8>视频</font>", metric), Paragraph(f"<b>{summary['evidence_count']}</b><br/><font size=8>证据样本</font>", metric), Paragraph(f"<b>{summary['stage_count']}</b><br/><font size=8>工序类型</font>", metric), Paragraph(f"<b>{pct(summary['combined_stage_accuracy'])}</b><br/><font size=8>综合准确率</font>", metric)]]
    stat_table = Table(stats, colWidths=[39.5 * mm] * 4)
    stat_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F4F8FB")), ("BOX", (0, 0), (-1, -1), 0.8, cyan), ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C8D6E0")), ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9)]))
    story += [stat_table, Paragraph("验真结论", h1), Paragraph("3 段真实来源视频形成 25 条抽样证据，覆盖气吹敷设 4 类工序与光纤熔接 5 类工序。小样本综合工序准确率 96.00%；该结果用于 Demo 验证，不构成生产精度承诺。", body), Paragraph("可信交付链", h1), Paragraph("源视频与关键帧 → 目标证据 → 工序判断 → 工程对象/验收规则 → 风险补证 → SHA-256 固化 → 数字档案。", body), PageBreak()]

    story += [Paragraph("01 · Air Blowing 气吹敷设验真", h1), Paragraph("两段现场视频、16 个抽帧，工序准确率 93.75%。唯一误判位于高速公路现场视频 18 秒，时间先验将仍在进行的气吹敷设提前判为完工检查。", body)]
    air_rows = [[Paragraph("视频", small), Paragraph("场景", small), Paragraph("正确/总数", small), Paragraph("准确率", small)]]
    for index, video in enumerate(reversed(air["videos"])):
        label = "高速公路通信现场" if video["video_id"] == "BV1u2Mv6METn" else "硅芯管高速气吹"
        air_rows.append([Paragraph(video["video_id"], small), Paragraph(label, body), Paragraph(f"{video['correct_stage_count']}/{video['sample_count']}", body), Paragraph(pct(video["stage_accuracy"]), body)])
    story += [styled_table(air_rows, [42 * mm, 66 * mm, 25 * mm, 27 * mm]), Paragraph("关键证据", h2)]
    frames = [air["evidence"][8], air["evidence"][12], air["evidence"][1], air["evidence"][5]]
    image_row, caption_row = [], []
    for item in frames:
        image_row.append(Image(str(ROOT / item["frame_path"]), width=37 * mm, height=22 * mm))
        caption_row.append(Paragraph(f"{item['video_id']}<br/>{item['timestamp']:.0f}s · {AIR_STAGE_ZH[item['construction_stage']]}", small))
    images = Table([image_row, caption_row], colWidths=[40 * mm] * 4)
    images.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#C8D6E0")), ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F4F8FB")), ("ALIGN", (0, 0), (-1, 0), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story += [images, Paragraph("工程对象—证据—验收规则", h2)]
    rule_rows = [[Paragraph("工序", small), Paragraph("工程对象", small), Paragraph("规则", small), Paragraph("证据状态", small)]]
    for stage in AIR_STAGE_ZH:
        item = next(e for e in air["evidence"] if e["construction_stage"] == stage)
        rule_rows.append([Paragraph(AIR_STAGE_ZH[stage], small), Paragraph(item["engineering_object"]["object_id"], small), Paragraph(item["acceptance_rule"]["rule_id"], small), Paragraph("已固化", small)])
    story += [styled_table(rule_rows, [35 * mm, 52 * mm, 36 * mm, 37 * mm]), Paragraph("应用价值", h2), Paragraph("自动拆解敷设工序，关联管道光缆段、关键帧和验收规则，用于施工过程监管、隐蔽工程影像验真与竣工档案生成。", body), PageBreak()]

    story += [Paragraph("02 · Fusion Splicing 光纤熔接验真", h1), Paragraph("视频对剥纤、清洁、切割、放入熔接机、熔接结果与保护套管处理进行了连续展示。9 个抽样证据覆盖 5 类工序，规则预测全部与人工复核一致。", body)]
    splice_rows = [[Paragraph("时间", small), Paragraph("工序", small), Paragraph("检测目标", small), Paragraph("置信度", small), Paragraph("哈希前缀", small)]]
    for item in splice:
        objects = "、".join(OBJECT_ZH[obj["label"]] for obj in item["detected_objects"])
        splice_rows.append([Paragraph(f"{item['timestamp']:.1f}s", small), Paragraph(SPLICE_STAGE_ZH[item["stage"]], small), Paragraph(objects, small), Paragraph(f"{item['confidence']:.2f}", small), Paragraph(item["evidence_hash"][:12], small)])
    story += [styled_table(splice_rows, [20 * mm, 28 * mm, 70 * mm, 20 * mm, 28 * mm]), Paragraph("目标覆盖与补证", h2), Paragraph("已覆盖：熔接机、光纤、热缩保护套管、熔接技术人员。目标词表中的接续盘 splice_tray 在本视频中未清晰出现，因此不生成虚假检出，并将其作为竣工归档前的影像补证项。", body), Paragraph("可信边界", h2), Paragraph("目标置信度来自人工复核领域标注，工序由轻量目标—时间规则推断。生产环境应使用通信施工领域数据训练 YOLO，并增加连续帧投票、接续损耗读数识别、工序顺序约束和监理签认。系统只提供辅助判断和可信证据整理，不替代法定验收。", body), Paragraph("交付物", h2), Paragraph("Air Blowing：construction_evidence.json<br/>Fusion Splicing：fiber_splicing_evidence.json<br/>全过程汇总：full_process_summary.json", small)]
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def main() -> None:
    air, splice, metrics = load()
    summary = build_summary(air, splice, metrics)
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(air, splice, metrics, summary)
    write_pdf(air, splice, metrics, summary)
    print(f"generated: {SUMMARY_PATH}")
    print(f"generated: {REPORT_MD_PATH}")
    print(f"generated: {REPORT_PDF_PATH}")


if __name__ == "__main__":
    main()
