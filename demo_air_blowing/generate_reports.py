from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo_air_blowing"
EVIDENCE_PATH = DEMO / "output" / "construction_evidence.json"
CROSS_REPORT_PATH = ROOT / "cross_scene_validation_report.md"
CROSS_JSON_PATH = DEMO / "output" / "cross_video_analysis.json"
REPORT_MD_PATH = DEMO / "output" / "高速公路通信工程光缆敷设施工智能验真报告.md"
REPORT_PDF_PATH = ROOT / "output" / "pdf" / "高速公路通信工程光缆敷设施工智能验真报告.pdf"

STAGE_ZH = {
    "equipment_setup": "设备布设",
    "cable_loading": "光缆上料",
    "blowing_process": "气吹敷设",
    "completion_check": "完工检查",
}
OBJECT_ZH = {
    "fiber_cable": "光缆",
    "blowing_machine": "吹缆机",
    "air_compressor": "空气压缩机",
    "worker": "施工人员",
    "cable_reel": "光缆盘",
    "safety_helmet": "安全帽",
}
TEST_NAMES = {
    "BV1u2Mv6METn": "测试集A：高速公路通信工程吹缆施工现场",
    "BV1Ld4y1X7AA": "测试集B：硅芯管高速气吹光缆施工",
}


def load_evidence() -> dict:
    return json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def labels(sample: dict) -> str:
    return "、".join(OBJECT_ZH[item["label"]] for item in sample["detected_objects"])


def build_cross_analysis(data: dict) -> dict:
    by_video: dict[str, list[dict]] = defaultdict(list)
    for sample in data["evidence"]:
        by_video[sample["video_id"]].append(sample)

    videos = []
    for video_id in ("BV1u2Mv6METn", "BV1Ld4y1X7AA"):
        meta = next(video for video in data["videos"] if video["video_id"] == video_id)
        samples = by_video[video_id]
        confusion = Counter(
            (item["ground_truth_stage"], item["construction_stage"]) for item in samples
        )
        videos.append(
            {
                "test_set": TEST_NAMES[video_id],
                "video_id": video_id,
                "title": meta["title"],
                "source_url": meta["source_url"],
                "sample_count": len(samples),
                "correct_count": sum(
                    item["ground_truth_stage"] == item["construction_stage"] for item in samples
                ),
                "stage_accuracy": meta["stage_accuracy"],
                "confusion": [
                    {"ground_truth": gt, "prediction": pred, "count": count}
                    for (gt, pred), count in sorted(confusion.items())
                ],
            }
        )
    return {
        "scene": data["scene"],
        "project_type": data["project_type"],
        "construction_environment": data["construction_environment"],
        "metric": "correct_stage_samples / reviewed_stage_samples",
        "overall": data["summary"],
        "videos": videos,
        "known_failure": {
            "video_id": "BV1u2Mv6METn",
            "timestamp": 18.0,
            "ground_truth": "blowing_process",
            "prediction": "completion_check",
            "cause": "短视频后段时间先验权重偏高，压过了吹缆机与光缆的目标证据。",
        },
    }


def write_cross_report(data: dict, analysis: dict) -> None:
    by_video: dict[str, list[dict]] = defaultdict(list)
    for sample in data["evidence"]:
        by_video[sample["video_id"]].append(sample)

    lines = [
        "# 高速公路通信工程光缆敷设施工跨场景验证报告",
        "",
        "> 系统定位：面向高速公路通信基础设施建设的光缆敷设施工智能监管与可信交付系统。",
        "",
        "## 1. 验证范围与口径",
        "",
        f"- 场景标签：`{data['scene']}`",
        f"- 项目类型：`{data['project_type']}`",
        f"- 施工环境：{data['construction_environment']}",
        "- 工序类别：`equipment_setup`、`cable_loading`、`blowing_process`、`completion_check`",
        "- 目标类别：`fiber_cable`、`blowing_machine`、`air_compressor`、`worker`、`cable_reel`、`safety_helmet`",
        "- 指标定义：工序识别准确率 = 工序预测正确抽帧数 / 人工复核抽帧总数。该指标为 Demo 小样本验证结果，不等同于生产模型精度承诺。",
        "",
        "## 2. 两个视频来源",
        "",
        "| 测试集 | 视频来源 | 时长 | 样本数 |",
        "|---|---|---:|---:|",
    ]
    for video_id in ("BV1u2Mv6METn", "BV1Ld4y1X7AA"):
        meta = next(video for video in data["videos"] if video["video_id"] == video_id)
        lines.append(
            f"| {TEST_NAMES[video_id]} | [{meta['title']}]({meta['source_url']}) | {meta['duration_seconds']:.2f}s | {meta['sample_count']} |"
        )

    lines += ["", "## 3. 测试样本与识别结果", ""]
    for video_id in ("BV1u2Mv6METn", "BV1Ld4y1X7AA"):
        lines += [
            f"### {TEST_NAMES[video_id]}",
            "",
            "| 时间戳 | 人工复核工序 | 模型工序 | 置信度 | 检出目标 | 结果 |",
            "|---:|---|---|---:|---|:---:|",
        ]
        for item in by_video[video_id]:
            result = (
                "正确"
                if item["ground_truth_stage"] == item["construction_stage"]
                else "误判"
            )
            lines.append(
                f"| {item['timestamp']:.0f}s | {STAGE_ZH[item['ground_truth_stage']]} | "
                f"{STAGE_ZH[item['construction_stage']]} | {item['confidence']:.2f} | {labels(item)} | {result} |"
            )
        lines.append("")

    video_a = next(item for item in analysis["videos"] if item["video_id"] == "BV1u2Mv6METn")
    video_b = next(item for item in analysis["videos"] if item["video_id"] == "BV1Ld4y1X7AA")
    summary = data["summary"]
    lines += [
        "## 4. 工序识别准确率",
        "",
        "| 范围 | 正确/总数 | 准确率 |",
        "|---|---:|---:|",
        f"| 测试集A | {video_a['correct_count']}/{video_a['sample_count']} | {pct(video_a['stage_accuracy'])} |",
        f"| 测试集B | {video_b['correct_count']}/{video_b['sample_count']} | {pct(video_b['stage_accuracy'])} |",
        f"| 跨场景总体 | {summary['correct_stage_count']}/{summary['sample_count']} | {pct(summary['stage_accuracy'])} |",
        "",
        "唯一误判位于测试集A的 18 秒：人工复核为“气吹敷设”，规则引擎预测为“完工检查”。原因是短视频后段的时间先验权重偏高，压过了吹缆机与光缆的目标证据。",
        "",
        "## 5. 泛化能力分析",
        "",
        "两个样本在画幅、机位、作业空间和剪辑节奏上存在明显差异：测试集A为高速公路通信施工现场实拍，测试集B呈现硅芯管高速气吹作业。系统在两段视频中均覆盖四类工序，并累计覆盖六类施工目标，说明“领域目标证据 + 时间规则”的轻量方案具备初步跨场景可迁移性。",
        "",
        "当前结论仍受样本规模限制。测试集A后段出现工序回切，暴露了固定时间先验对非线性剪辑的敏感性。生产化应引入连续帧投票、工序状态转移约束和面向吹缆设备的自定义 YOLO 权重，并在不同道路、隧道、天气和昼夜条件下扩大独立测试集。",
        "",
        "## 6. 应用价值",
        "",
        "- 通信基础设施施工过程监管：把施工视频自动拆解为可查询的工序证据链。",
        "- 隐蔽工程影像验真：以时间戳、画面哈希、对象识别和规则结论建立可追溯证据。",
        "- 竣工数字档案生成：按工程对象归档抽帧、风险记录、验收结论和来源视频。",
        "- 效率估算：按人工整理 5 分钟/帧、AI 辅助复核 0.5 分钟/帧计算，本次 16 帧由约 80 分钟降至约 8 分钟，预计节省 90%；该值为流程估算，需在真实项目中计时验证。",
        "",
        "## 7. 可信边界",
        "",
        "本报告使用真实来源视频的抽帧和人工复核领域标注验证工序规则；目标置信度属于 Demo 标注配置，不应作为未经复测的现场模型指标。所有中高风险项均保持 `manual_review_required`，不替代监理或验收人员签认。",
    ]
    CROSS_REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_verification_markdown(data: dict) -> None:
    summary = data["summary"]
    risk_items = [item for item in data["evidence"] if item["risk_detection"]]
    lines = [
        "# 高速公路通信工程光缆敷设施工智能验真报告",
        "",
        f"- 系统：{data['system_name']}",
        f"- 施工环境：{data['construction_environment']}",
        f"- 场景 / 项目类型：`{data['scene']}` / `{data['project_type']}`",
        f"- 视频 / 抽帧：{summary['video_count']} 段 / {summary['sample_count']} 帧",
        f"- 工序识别：{summary['correct_stage_count']}/{summary['sample_count']}，准确率 {pct(summary['stage_accuracy'])}",
        f"- 效率估算：人工 {summary['efficiency_estimate']['manual_minutes']:.0f} 分钟 / AI辅助 {summary['efficiency_estimate']['ai_assisted_minutes']:.0f} 分钟，预计节省 {pct(summary['efficiency_estimate']['time_reduction_rate'])}",
        "",
        "## 验真结论",
        "",
        "两段样例视频均形成“来源视频—时间戳—关键帧—检测目标—施工阶段—工程对象—风险项”的可追溯证据链。四类施工阶段和六类目标均得到覆盖；总体工序识别准确率为 93.75%，满足比赛 Demo 的跨场景演示目标。",
        "",
        "## 风险记录",
        "",
    ]
    for item in risk_items:
        risks = "、".join(risk["risk"] for risk in item["risk_detection"])
        lines.append(f"- {item['video_id']} @ {item['timestamp']:.0f}s：{risks}，需人工复核。")
    lines += [
        "",
        "## 应用价值",
        "",
        "1. 通信基础设施施工过程监管。",
        "2. 隐蔽工程影像验真。",
        "3. 竣工数字档案生成。",
        "",
        "## 可信说明",
        "",
        "当前随包视频采用人工复核目标标注与轻量时间规则；新视频需要加载自定义 YOLO 权重或补充领域标注。系统输出用于辅助监管与证据整理，不替代法定验收签认。",
    ]
    REPORT_MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def find_chinese_font() -> str:
    candidates = [
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError("未找到可用中文字体")


def write_pdf(data: dict) -> None:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        Image,
        KeepTogether,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    REPORT_PDF_PATH.parent.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(TTFont("CN", find_chinese_font()))
    navy = colors.HexColor("#17324D")
    cyan = colors.HexColor("#00A6A6")
    pale = colors.HexColor("#EAF7F6")
    gray = colors.HexColor("#5D6B78")
    styles = getSampleStyleSheet()
    title = ParagraphStyle("TitleCN", parent=styles["Title"], fontName="CN", fontSize=22, leading=30, textColor=navy, alignment=TA_CENTER, spaceAfter=10 * mm)
    h1 = ParagraphStyle("H1CN", parent=styles["Heading1"], fontName="CN", fontSize=15, leading=21, textColor=navy, spaceBefore=5 * mm, spaceAfter=3 * mm)
    h2 = ParagraphStyle("H2CN", parent=styles["Heading2"], fontName="CN", fontSize=12, leading=17, textColor=cyan, spaceBefore=3 * mm, spaceAfter=2 * mm)
    body = ParagraphStyle("BodyCN", parent=styles["BodyText"], fontName="CN", fontSize=9.5, leading=15, textColor=colors.HexColor("#263746"), alignment=TA_LEFT)
    small = ParagraphStyle("SmallCN", parent=body, fontSize=7.5, leading=11, textColor=gray)
    metric = ParagraphStyle("MetricCN", parent=body, fontSize=15, leading=19, textColor=navy, alignment=TA_CENTER)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D5E0E8"))
        canvas.line(18 * mm, 14 * mm, 192 * mm, 14 * mm)
        canvas.setFont("CN", 7)
        canvas.setFillColor(gray)
        canvas.drawString(18 * mm, 9 * mm, "通信基建 AI 施工过程智能验真与可信交付")
        canvas.drawRightString(192 * mm, 9 * mm, f"第 {doc.page} 页")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(REPORT_PDF_PATH), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=19 * mm, title="高速公路通信工程光缆敷设施工智能验真报告", author="通信基建施工管理系统")
    story = [
        Spacer(1, 9 * mm),
        Paragraph("高速公路通信工程光缆敷设施工智能验真报告", title),
        Paragraph("面向高速公路通信基础设施建设的光缆敷设施工智能监管与可信交付系统", ParagraphStyle("Sub", parent=body, alignment=TA_CENTER, fontSize=11, leading=18, textColor=gray)),
        Spacer(1, 10 * mm),
    ]
    info = [
        [Paragraph("场景标签", small), Paragraph(data["scene"], small)],
        [Paragraph("项目类型", small), Paragraph(data["project_type"], small)],
        [Paragraph("施工环境", small), Paragraph(data["construction_environment"], body)],
    ]
    info_table = Table(info, colWidths=[32 * mm, 126 * mm], hAlign="CENTER")
    info_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, -1), pale), ("TEXTCOLOR", (0, 0), (-1, -1), navy), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C8D6E0")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story += [info_table, Spacer(1, 8 * mm)]
    s = data["summary"]
    metrics = [[Paragraph(f"<b>{s['video_count']}</b><br/><font size=8>视频样本</font>", metric), Paragraph(f"<b>{s['sample_count']}</b><br/><font size=8>证据帧</font>", metric), Paragraph(f"<b>{s['correct_stage_count']}/{s['sample_count']}</b><br/><font size=8>工序正确</font>", metric), Paragraph(f"<b>{pct(s['stage_accuracy'])}</b><br/><font size=8>工序准确率</font>", metric)]]
    metrics_table = Table(metrics, colWidths=[39.5 * mm] * 4)
    metrics_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F4F8FB")), ("BOX", (0, 0), (-1, -1), 0.8, cyan), ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C8D6E0")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9)]))
    story += [metrics_table, Paragraph("验真结论", h1), Paragraph("两段真实来源视频均形成“来源视频—时间戳—关键帧—目标—工序—工程对象—风险”的可追溯证据链。四类工序和六类目标全部覆盖；跨场景总体工序识别准确率为 93.75%。", body), Paragraph("应用价值", h1)]
    value_table = Table([[Paragraph("01", metric), Paragraph("通信基础设施施工过程监管", body)], [Paragraph("02", metric), Paragraph("隐蔽工程影像验真", body)], [Paragraph("03", metric), Paragraph("竣工数字档案生成", body)]], colWidths=[22 * mm, 136 * mm])
    value_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, -1), pale), ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#C8D6E0")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story += [value_table, PageBreak(), Paragraph("跨场景验证结果", h1)]
    test_rows = [[Paragraph("测试集", small), Paragraph("来源与场景", small), Paragraph("正确/总数", small), Paragraph("准确率", small)]]
    order = ["BV1u2Mv6METn", "BV1Ld4y1X7AA"]
    for idx, video_id in enumerate(order):
        video = next(item for item in data["videos"] if item["video_id"] == video_id)
        test_rows.append([Paragraph(chr(65 + idx), metric), Paragraph(f"{video['title']}<br/><font size=7>{video_id}</font>", body), Paragraph(f"{video['correct_stage_count']}/{video['sample_count']}", body), Paragraph(pct(video["stage_accuracy"]), body)])
    test_table = Table(test_rows, colWidths=[18 * mm, 92 * mm, 25 * mm, 25 * mm], repeatRows=1)
    test_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), navy), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C8D6E0")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story += [test_table, Spacer(1, 5 * mm)]
    sample_by_video = defaultdict(list)
    for item in data["evidence"]:
        sample_by_video[item["video_id"]].append(item)
    frame_choices = {"BV1u2Mv6METn": [0, 4], "BV1Ld4y1X7AA": [1, 5]}
    for idx, video_id in enumerate(order):
        video = next(item for item in data["videos"] if item["video_id"] == video_id)
        samples = sample_by_video[video_id]
        story.append(Paragraph(TEST_NAMES[video_id], h2))
        images = []
        captions = []
        for sample_index in frame_choices[video_id]:
            item = samples[sample_index]
            frame = ROOT / item["frame_path"]
            img = Image(str(frame), width=76 * mm, height=43 * mm)
            images.append(img)
            captions.append(Paragraph(f"{item['timestamp']:.0f}s · {STAGE_ZH[item['construction_stage']]} · 置信度 {item['confidence']:.2f}", small))
        evidence_table = Table([images, captions], colWidths=[79 * mm, 79 * mm])
        evidence_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (0, 0), (-1, 0), "CENTER"), ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F4F8FB")), ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#C8D6E0")), ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C8D6E0")), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        story += [KeepTogether([Paragraph(f"视频 {video_id}，{video['sample_count']} 个抽帧，工序准确率 {pct(video['stage_accuracy'])}。", body), Spacer(1, 2 * mm), evidence_table]), Spacer(1, 3 * mm)]
    story += [Paragraph("异常与风险", h1)]
    risks = [item for item in data["evidence"] if item["risk_detection"]]
    risk_rows = [[Paragraph("视频/时间", small), Paragraph("风险", small), Paragraph("处置", small)]]
    for item in risks:
        for risk in item["risk_detection"]:
            risk_rows.append([Paragraph(f"{item['video_id']} / {item['timestamp']:.0f}s", small), Paragraph(risk["risk"], small), Paragraph("人工复核", small)])
    risk_table = Table(risk_rows, colWidths=[48 * mm, 77 * mm, 33 * mm], repeatRows=1)
    risk_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), navy), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C8D6E0")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story += [risk_table, Paragraph("可信边界与改进建议", h1), Paragraph("唯一误判位于测试集A的 18 秒：实际仍为气吹敷设，规则引擎受短视频后段时间先验影响提前判为完工检查。当前随包样例使用人工复核领域标注验证规则流程；新视频需配置自定义 YOLO 权重。建议生产化引入连续帧投票、状态转移约束并扩大跨道路、隧道、天气和昼夜条件测试。系统结果用于辅助监管，不替代法定验收签认。", body), Spacer(1, 4 * mm), Paragraph("证据输出：demo_air_blowing/output/construction_evidence.json<br/>跨场景报告：cross_scene_validation_report.md", small)]
    stage_rules = []
    for stage in ("equipment_setup", "cable_loading", "blowing_process", "completion_check"):
        sample = next(item for item in data["evidence"] if item["construction_stage"] == stage)
        rule = sample["acceptance_rule"]
        stage_rules.append([
            Paragraph(STAGE_ZH[stage], small),
            Paragraph(sample["engineering_object"]["object_id"], small),
            Paragraph(f"{sample['video_id']} / {sample['timestamp']:.0f}s / SHA256", small),
            Paragraph(f"{rule['rule_id']}<br/>{rule['name']}", small),
        ])
    rule_rows = [[Paragraph("工序", small), Paragraph("工程对象", small), Paragraph("施工证据", small), Paragraph("验收规则", small)]] + stage_rules
    rule_table = Table(rule_rows, colWidths=[27 * mm, 37 * mm, 43 * mm, 51 * mm], repeatRows=1)
    rule_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), navy), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C8D6E0")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    eff = s["efficiency_estimate"]
    story += [Paragraph("工程对象—施工证据—验收规则关联", h1), rule_table, Paragraph("效率提升估算", h1), Paragraph(f"按人工逐帧整理 5 分钟/帧、AI 辅助复核 0.5 分钟/帧的 Demo 口径，16 帧证据由约 {eff['manual_minutes']:.0f} 分钟降至约 {eff['ai_assisted_minutes']:.0f} 分钟，预计节省 {pct(eff['time_reduction_rate'])}。该数字为流程估算，需在真实项目中通过计时实验验证。", body)]
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def main() -> None:
    data = load_evidence()
    analysis = build_cross_analysis(data)
    CROSS_JSON_PATH.write_text(json.dumps(analysis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_cross_report(data, analysis)
    write_verification_markdown(data)
    write_pdf(data)
    print(f"generated: {CROSS_REPORT_PATH}")
    print(f"generated: {CROSS_JSON_PATH}")
    print(f"generated: {REPORT_MD_PATH}")
    print(f"generated: {REPORT_PDF_PATH}")


if __name__ == "__main__":
    main()
