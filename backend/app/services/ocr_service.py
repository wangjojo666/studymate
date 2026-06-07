from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.config import settings


@dataclass(frozen=True)
class OcrResult:
    pages: list[tuple[int, str]]
    total_pages: int
    processed_pages: int


def ocr_pdf_with_qwen_vl(
    path: Path,
    start_page: int,
    max_pages: int,
    mode: str = "fast",
    on_page_done: Callable[[int, str], None] | None = None,
    on_page_start: Callable[[int], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> OcrResult:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("缺少 PyMuPDF，无法把扫描版 PDF 渲染成图片。") from exc

    if settings.ocr_llm_provider != "ollama":
        raise RuntimeError("当前 OCR 仅支持 Ollama 视觉模型，请把 OCR_LLM_PROVIDER 设置为 ollama。")

    base_url = (settings.ocr_llm_base_url or "http://127.0.0.1:11434").rstrip("/")
    model = settings.ocr_llm_model or "qwen3-vl:30b"
    max_pages = min(max_pages, settings.ocr_max_pages_per_request)
    mode = mode if mode in {"fast", "full"} else "fast"
    render_scale = 0.9 if mode == "fast" else 1.35

    pages: list[tuple[int, str]] = []
    with fitz.open(str(path)) as document:
        total_pages = document.page_count
        if start_page > total_pages:
            raise RuntimeError(f"起始页超过 PDF 总页数。当前 PDF 共 {total_pages} 页。")
        end_page = min(total_pages, start_page + max_pages - 1)
        for page_number in range(start_page, end_page + 1):
            if should_stop and should_stop():
                break
            if on_page_start:
                on_page_start(page_number)
            page = document[page_number - 1]
            pixmap = page.get_pixmap(matrix=fitz.Matrix(render_scale, render_scale), alpha=False)
            image_base64 = base64.b64encode(pixmap.tobytes("png")).decode("ascii")
            text = _ocr_single_page(base_url, model, image_base64, page_number, mode)
            pages.append((page_number, text.strip()))
            if on_page_done:
                on_page_done(page_number, text.strip())

    return OcrResult(pages=pages, total_pages=total_pages, processed_pages=len(pages))


def _ocr_single_page(
    base_url: str,
    model: str,
    image_base64: str,
    page_number: int,
    mode: str,
) -> str:
    if mode == "fast":
        system_prompt = (
            "你是课程资料快速索引助手。请根据图片抽取可用于检索和问答的学习要点，"
            "不要逐字抄全文，不要解释图片之外的内容。"
        )
        user_prompt = (
            f"请快速读取第 {page_number} 页，输出 600 字以内的中文索引内容，包含："
            "1. 页标题或章节；2. 核心概念；3. 重要公式/定理；4. 例题或题型关键词；"
            "5. 易错点。公式尽量用 LaTeX 或纯文本表达。"
        )
        num_predict = 900
        timeout = 120
    else:
        system_prompt = (
            "你是严谨的 OCR 引擎。只识别图片中的教材文字、公式、标题和页眉页脚。"
            "不要解释，不要总结，不要编造看不清的内容。"
        )
        user_prompt = (
            f"请识别第 {page_number} 页图片中的全部可见文字。"
            "保持原有段落顺序；数学公式尽量用 LaTeX 或纯文本表达。"
        )
        num_predict = 3500
        timeout = 240
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
                "images": [image_base64],
            },
        ],
        "options": {
            "temperature": 0,
            "num_predict": num_predict,
        },
        "think": False,
        "keep_alive": "10m",
    }
    request = urllib.request.Request(
        f"{base_url}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"无法连接本地 Ollama OCR 服务。请先启动：ollama run {model}") from exc
    except TimeoutError as exc:
        raise RuntimeError("本地 OCR 超时。可以减少页数后重试。") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("本地 OCR 返回格式异常。") from exc

    return (body.get("message") or {}).get("content", "").strip()
