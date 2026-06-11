from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from html import escape
from io import BytesIO

from sqlalchemy.orm import Session

from app.models.entities import ChatMessage, Course, Document, QuestionAttempt, ReviewTask, User
from app.services.learning_service import get_learning_profile, get_wrong_attempts
from app.services.llm_service import call_llm


def generate_learning_report_pdf(db: Session, course_id: int, user_id: str | None = None) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:
        return _generate_simple_report_pdf(db, course_id, user_id)

    course = db.get(Course, course_id)
    if course is None:
        raise ValueError("课程不存在")

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    font_name = "STSong-Light"
    profile = get_learning_profile(db, course_id, user_id)
    wrong_attempts = get_wrong_attempts(db, course_id, limit=50, user_id=user_id)
    user = _load_user(db, user_id)
    documents = (
        db.query(Document)
        .filter(Document.course_id == course_id)
        .order_by(Document.created_at.asc())
        .all()
    )
    review_query = db.query(ReviewTask).filter(ReviewTask.course_id == course_id)
    if user_id:
        review_query = review_query.filter(ReviewTask.user_id == str(user_id))
    review_tasks = review_query.order_by(ReviewTask.deadline.asc().nullslast(), ReviewTask.created_at.desc()).limit(12).all()
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
    lead_style = ParagraphStyle(
        "StudyMateLead",
        parent=body_style,
        fontName=font_name,
        fontSize=11,
        leading=18,
        textColor=colors.HexColor("#1f2937"),
        spaceAfter=6,
    )

    story = [
        Paragraph("StudyMate 学习诊断报告", title_style),
        Paragraph(f"课程名称：{escape(course.name)}", lead_style),
        Paragraph(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}", body_style),
        Paragraph(f"用户：{escape(_user_label(user, user_id))}", body_style),
        Spacer(1, 8),
        Paragraph("学习总览", heading_style),
        _overview_table(db, course_id, profile, body_style, Table, TableStyle, colors),
        Paragraph("薄弱知识点 Top 5", heading_style),
        _weak_points_table(profile, body_style, Table, TableStyle, colors),
        Paragraph("错题原因分布", heading_style),
        _wrong_reason_table(wrong_attempts, body_style, Table, TableStyle, colors),
        Paragraph("最近错题分析", heading_style),
        _recent_wrong_table(wrong_attempts, body_style, Table, TableStyle, colors),
        Paragraph("复习计划", heading_style),
        _review_plan_table(review_tasks, profile, body_style, Table, TableStyle, colors),
        Paragraph("AI 建议", heading_style),
        Paragraph(_paragraph(advice), body_style),
        Paragraph("来源说明", heading_style),
        _source_table(documents, body_style, Table, TableStyle, colors),
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


def _load_user(db: Session, user_id: str | None) -> User | None:
    if not user_id or not str(user_id).isdigit():
        return None
    return db.get(User, int(user_id))


def _user_label(user: User | None, user_id: str | None) -> str:
    if user is None:
        return str(user_id or "未登录用户")
    name = user.display_name or user.email
    return f"{name}（{user.email}）"


def _overview_table(db: Session, course_id: int, profile: dict, body_style, Table, TableStyle, colors):
    summary = profile.get("summary", {})
    question_count = db.query(ChatMessage).filter(ChatMessage.course_id == course_id).count()
    practice_count = db.query(QuestionAttempt).filter(QuestionAttempt.course_id == course_id).count()
    rows = [
        ["指标", "数值", "说明"],
        ["上传资料数", str(summary.get("document_count", 0)), "课程已保存的 PDF/PPTX/DOCX/TXT/图片资料"],
        ["知识片段数", str(summary.get("chunk_count", 0)), "已入库并可参与检索的资料片段"],
        ["提问次数", str(question_count), "课程问答记录数"],
        ["练习次数", str(practice_count), "写入错题本或学习画像的练习记录"],
        ["正确率", f"{summary.get('practice_accuracy', 0)}%", "基于已记录练习结果"],
        ["总体掌握度", f"{summary.get('overall_mastery', 0)}%", "知识点掌握度均值，范围 0-100"],
    ]
    return _table(rows, body_style, Table, TableStyle, colors, widths=[30, 26, 118])


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
    rows = [["排名", "知识点", "掌握度", "错题", "主要错因", "推荐复习动作"]]
    if not points:
        rows.append(["-", "暂无", "-", "-", "暂无", "先上传资料并记录练习结果。"])
    for index, point in enumerate(points, start=1):
        rows.append(
            [
                str(index),
                point.get("name", ""),
                f"{point.get('mastery_score', 0)}%",
                str(point.get("wrong_count", 0)),
                point.get("main_error_label") or "未分类",
                point.get("explanation") or f"回看 P{point.get('source_page') or '-'}，做 3 道同类题。",
            ]
        )
    return _table(rows, body_style, Table, TableStyle, colors, widths=[14, 34, 20, 16, 28, 62])


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


def _recent_wrong_table(wrong_attempts: list[dict], body_style, Table, TableStyle, colors):
    rows = [["题目", "用户答案", "正确答案", "错因", "关联知识点"]]
    if not wrong_attempts:
        rows.append(["暂无数据", "暂无数据", "暂无数据", "暂无数据", "暂无数据"])
    for item in wrong_attempts[:8]:
        rows.append(
            [
                _short(item.get("question_text"), 90),
                _short(item.get("user_answer") or "未填写", 60),
                _short(item.get("correct_answer") or "未填写", 60),
                item.get("error_reason") or "未分类",
                item.get("knowledge_point_name") or "未标注",
            ]
        )
    return _table(rows, body_style, Table, TableStyle, colors, widths=[48, 32, 32, 30, 32])


def _review_plan_table(review_tasks: list[ReviewTask], profile: dict, body_style, Table, TableStyle, colors):
    rows = [["日期", "任务标题", "任务类型", "状态"]]
    tasks = review_tasks[:8]
    if not tasks and profile.get("recommendations"):
        today = datetime.now().date()
        for index, item in enumerate(profile.get("recommendations", [])[:5]):
            rows.append(
                [
                    (today + timedelta(days=index)).isoformat(),
                    item.get("title", ""),
                    item.get("difficulty", "review"),
                    "建议执行",
                ]
            )
    elif not tasks:
        rows.append([datetime.now().date().isoformat(), "暂无数据：先上传资料并记录练习", "初始化", "待生成"])
    else:
        for task in tasks:
            rows.append(
                [
                    _date_text(task.deadline),
                    task.title,
                    task.task_type,
                    task.status,
                ]
            )
    return _table(rows, body_style, Table, TableStyle, colors, widths=[30, 78, 34, 32])


def _source_table(documents: list[Document], body_style, Table, TableStyle, colors):
    rows = [["资料名", "页码/来源", "片段数", "状态"]]
    if not documents:
        rows.append(["暂无数据", "暂无数据", "0", "暂无资料"])
    for document in documents[:12]:
        page_text = f"1-{document.page_count} 页" if document.page_count else "暂无页码"
        rows.append(
            [
                document.original_filename,
                page_text,
                str(document.chunk_count),
                document.status,
            ]
        )
    return _table(rows, body_style, Table, TableStyle, colors, widths=[78, 36, 24, 36])


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


def _short(value: object, limit: int) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split())
    return text if len(text) <= limit else f"{text[:limit]}..."


def _generate_simple_report_pdf(db: Session, course_id: int, user_id: str | None) -> bytes:
    course = db.get(Course, course_id)
    if course is None:
        raise ValueError("课程不存在")

    profile = get_learning_profile(db, course_id, user_id)
    wrong_attempts = get_wrong_attempts(db, course_id, limit=20, user_id=user_id)
    summary = profile.get("summary", {})
    lines = [
        f"StudyMate Learning Report - {course.name}",
        f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "Overview",
        f"Study actions: {summary.get('study_actions', 0)}",
        f"Overall mastery: {summary.get('overall_mastery', 0)}%",
        f"Practice accuracy: {summary.get('practice_accuracy', 0)}%",
        f"Knowledge points: {summary.get('knowledge_point_count', 0)}",
        f"Chunks: {summary.get('chunk_count', 0)}",
        "",
        "Weak Points",
    ]
    for index, point in enumerate(profile.get("weak_points", [])[:5], start=1):
        lines.append(
            f"{index}. {point.get('name', '')} - {point.get('mastery_score', 0)}%, wrong {point.get('wrong_count', 0)}"
        )
    if not profile.get("weak_points"):
        lines.append("No weak points yet.")

    lines.extend(["", "Wrong Reasons"])
    reason_counts = Counter(item.get("error_reason") or "unlabeled" for item in wrong_attempts)
    if reason_counts:
        for reason, count in reason_counts.most_common(6):
            lines.append(f"{reason}: {count}")
    else:
        lines.append("No wrong attempts yet.")

    lines.extend(["", "Review Plan"])
    for item in profile.get("recommendations", [])[:5]:
        lines.append(f"- {item.get('title', '')}: {item.get('action', '')}")
    lines.extend(["", "AI Advice", _ai_advice(course.name, profile, wrong_attempts)])
    return _build_minimal_pdf(lines)


def _build_minimal_pdf(lines: list[str]) -> bytes:
    escaped_lines = [_pdf_escape(_ascii_line(line)[:110]) for line in lines[:44]]
    commands = ["BT", "/F1 12 Tf", "50 790 Td", "16 TL"]
    for line in escaped_lines:
        commands.append(f"({line}) Tj")
        commands.append("T*")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1", errors="replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(pdf)


def _ascii_line(value: object) -> str:
    return str(value).encode("latin-1", errors="replace").decode("latin-1")


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
