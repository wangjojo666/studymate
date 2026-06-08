from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from html import escape
from io import BytesIO

from sqlalchemy.orm import Session

from app.models.entities import Course
from app.services.learning_service import get_learning_profile, get_wrong_attempts
from app.services.llm_service import call_llm


def generate_learning_report_pdf(db: Session, course_id: int) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:
        raise RuntimeError("缺少 reportlab，无法生成 PDF 学习报告。请安装 requirements.txt。") from exc

    course = db.get(Course, course_id)
    if course is None:
        raise ValueError("课程不存在")

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    font_name = "STSong-Light"
    profile = get_learning_profile(db, course_id)
    wrong_attempts = get_wrong_attempts(db, course_id, limit=50)
    advice = _ai_advice(course.name, profile, wrong_attempts)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"{course.name} StudyMate 学习报告",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "StudyMateTitle",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=22,
        leading=28,
        textColor=colors.HexColor("#0f172a"),
    )
    heading_style = ParagraphStyle(
        "StudyMateHeading",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=14,
        leading=20,
        spaceBefore=10,
        spaceAfter=7,
        textColor=colors.HexColor("#1d4ed8"),
    )
    body_style = ParagraphStyle(
        "StudyMateBody",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=9.5,
        leading=15,
        textColor=colors.HexColor("#334155"),
    )

    story = [
        Paragraph(f"{escape(course.name)} 学习报告", title_style),
        Paragraph(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}", body_style),
        Spacer(1, 8),
        Paragraph("学习总览", heading_style),
        _summary_table(profile, body_style, Table, TableStyle, colors),
        Paragraph("薄弱知识点 Top 5", heading_style),
        _weak_points_table(profile, body_style, Table, TableStyle, colors),
        Paragraph("错题原因分布", heading_style),
        _wrong_reason_table(wrong_attempts, body_style, Table, TableStyle, colors),
        Paragraph("最近练习记录", heading_style),
        _recent_attempts_table(profile, body_style, Table, TableStyle, colors),
        Paragraph("下周复习计划", heading_style),
        _next_week_plan(profile, body_style, Table, TableStyle, colors),
        Paragraph("AI 建议", heading_style),
        Paragraph(_paragraph(advice), body_style),
    ]

    def draw_footer(canvas, document):
        canvas.saveState()
        canvas.setFont(font_name, 8)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(18 * mm, 10 * mm, "StudyMate AI 学习画像系统")
        canvas.drawRightString(192 * mm, 10 * mm, f"第 {document.page} 页")
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
    return buffer.getvalue()


def _summary_table(profile: dict, body_style, Table, TableStyle, colors):
    summary = profile.get("summary", {})
    rows = [
        ["指标", "数值", "说明"],
        ["学习行为", str(summary.get("study_actions", 0)), "提问、练习、生成材料等总次数"],
        ["总体掌握度", f"{summary.get('overall_mastery', 0)}%", "知识点掌握均值，含遗忘衰减"],
        ["练习正确率", f"{summary.get('practice_accuracy', 0)}%", "基于已记录练习结果"],
        ["知识点数量", str(summary.get("knowledge_point_count", 0)), "由资料和课程名称抽取"],
        ["资料片段", str(summary.get("chunk_count", 0)), "已入库可检索知识片段"],
    ]
    return _table(rows, body_style, Table, TableStyle, colors, widths=[30, 26, 118])


def _weak_points_table(profile: dict, body_style, Table, TableStyle, colors):
    points = profile.get("weak_points", [])[:5]
    rows = [["排名", "知识点", "掌握度", "错题", "建议"]]
    if not points:
        rows.append(["-", "暂无", "-", "-", "先上传资料并记录练习结果。"])
    for index, point in enumerate(points, start=1):
        rows.append(
            [
                str(index),
                point.get("name", ""),
                f"{point.get('mastery_score', 0)}%",
                str(point.get("wrong_count", 0)),
                f"回看 P{point.get('source_page') or '-'}，做 3 道同类题。",
            ]
        )
    return _table(rows, body_style, Table, TableStyle, colors, widths=[16, 42, 24, 18, 74])


def _wrong_reason_table(wrong_attempts: list[dict], body_style, Table, TableStyle, colors):
    counts = Counter(item.get("error_reason") or "未标注" for item in wrong_attempts)
    rows = [["错因", "次数", "复盘动作"]]
    if not counts:
        rows.append(["暂无错题", "0", "本周至少记录 3 道练习，形成诊断样本。"])
    for reason, count in counts.most_common(6):
        rows.append([reason, str(count), _review_action_for_reason(reason)])
    return _table(rows, body_style, Table, TableStyle, colors, widths=[40, 20, 114])


def _recent_attempts_table(profile: dict, body_style, Table, TableStyle, colors):
    attempts = profile.get("recent_attempts", [])[:6]
    rows = [["时间", "知识点", "结果", "错因/备注"]]
    if not attempts:
        rows.append(["-", "暂无", "-", "先在诊断页写入一次练习记录。"])
    for item in attempts:
        rows.append(
            [
                _date_text(item.get("created_at")),
                item.get("knowledge_point_name") or "未标注",
                "正确" if item.get("is_correct") else "错误",
                item.get("error_reason") or item.get("difficulty_label") or "",
            ]
        )
    return _table(rows, body_style, Table, TableStyle, colors, widths=[34, 42, 22, 76])


def _next_week_plan(profile: dict, body_style, Table, TableStyle, colors):
    recommendations = profile.get("recommendations", [])[:5]
    start = datetime.now().date()
    rows = [["日期", "复习任务", "训练方式"]]
    if not recommendations:
        rows.append([start.isoformat(), "补充课程资料并同步知识点", "上传资料后生成提纲和练习"])
    for index, item in enumerate(recommendations):
        day = start + timedelta(days=index)
        rows.append([day.isoformat(), item.get("title", ""), item.get("action", "")])
    return _table(rows, body_style, Table, TableStyle, colors, widths=[32, 54, 88])


def _table(rows: list[list[str]], body_style, Table, TableStyle, colors, widths: list[int]):
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph

    data = [[Paragraph(_paragraph(cell), body_style) for cell in row] for row in rows]
    table = Table(data, colWidths=[width * mm for width in widths], repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eff6ff")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _ai_advice(course_name: str, profile: dict, wrong_attempts: list[dict]) -> str:
    weak_names = [item.get("name", "") for item in profile.get("weak_points", [])[:5]]
    reason_counts = Counter(item.get("error_reason") or "未标注" for item in wrong_attempts)
    messages = [
        {
            "role": "system",
            "content": "你是大学课程复习教练。根据学习画像给出简洁、可执行的中文建议。",
        },
        {
            "role": "user",
            "content": (
                f"课程：{course_name}\n"
                f"总览：{profile.get('summary', {})}\n"
                f"薄弱点：{weak_names}\n"
                f"错因：{dict(reason_counts)}\n"
                "请给出 4 条下周复习建议，每条不超过 35 字。"
            ),
        },
    ]
    response = call_llm(messages, temperature=0.2)
    if response:
        return response.content
    if weak_names:
        return (
            f"优先复习 {weak_names[0]}，每天用 20 分钟回看资料并做同类题；"
            "错题要写清错误原因，第二天用变式题复测；每周至少导出一次报告观察掌握度变化。"
        )
    return "先上传课程资料并完成一次问答、一次练习记录，系统会据此生成更准确的复习建议。"


def _review_action_for_reason(reason: str) -> str:
    if "公式" in reason:
        return "整理公式条件和适用范围，再做代入练习。"
    if "概念" in reason:
        return "重读定义，用自己的话写出反例和例子。"
    if "步骤" in reason:
        return "补全推导步骤，训练规范书写。"
    if "题型" in reason:
        return "按题型归类，比较同类题的触发条件。"
    return "回看对应知识点，做 2 道基础题和 1 道变式题。"


def _date_text(value: object) -> str:
    if not value:
        return "-"
    text = str(value)
    return text[:10]


def _paragraph(value: object) -> str:
    text = "" if value is None else str(value)
    return escape(text).replace("\n", "<br/>")
