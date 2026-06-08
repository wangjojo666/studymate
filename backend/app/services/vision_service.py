from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from pathlib import Path

from app.config import settings


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def describe_courseware_image(path: Path, course_name: str) -> str:
    provider = settings.ocr_llm_provider
    if provider in {"mock", "offline"}:
        return _mock_image_description(path, course_name)
    if provider != "ollama":
        raise RuntimeError("当前图片课件识别需要 OCR_LLM_PROVIDER=ollama 或 mock。")

    base_url = (settings.ocr_llm_base_url or "http://127.0.0.1:11434").rstrip("/")
    model = settings.ocr_llm_model or "qwen3-vl:30b"
    image_base64 = base64.b64encode(path.read_bytes()).decode("ascii")
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是 StudyMate 的多模态课件理解助手。只根据图片内容识别可入库知识，"
                    "重点覆盖数学公式、流程图、代码截图、物理电路图、表格和课堂板书。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"课程名称：{course_name}\n"
                    "请把这张课件/题目/代码/电路图片转成可检索的中文知识库文本。输出结构："
                    "1. 图片类型；2. 识别到的文字或代码；3. 关键公式/符号；"
                    "4. 图中流程或电路关系；5. 可作为知识点的考点；6. 易错提醒。"
                    "如果看不清，请明确标注不确定内容，不要编造。"
                ),
                "images": [image_base64],
            },
        ],
        "options": {"temperature": 0, "num_predict": 1800},
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
        with urllib.request.urlopen(request, timeout=180) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"无法连接本地视觉识别服务。请先启动：ollama run {model}") from exc
    except TimeoutError as exc:
        raise RuntimeError("图片课件识别超时。请确认本地视觉模型已启动，或换用更小图片。") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("图片课件识别服务返回格式异常。") from exc

    content = (body.get("message") or {}).get("content", "").strip()
    if not content:
        raise RuntimeError("视觉模型未返回可入库内容。")
    return _normalize_image_description(content, path, course_name)


def _normalize_image_description(content: str, path: Path, course_name: str) -> str:
    return (
        f"图片课件来源：{path.name}\n"
        f"课程：{course_name}\n"
        "识别结果：\n"
        f"{content.strip()}"
    )


def _mock_image_description(path: Path, course_name: str) -> str:
    stem = path.stem.replace("_", " ").replace("-", " ").strip() or path.name
    return (
        f"图片课件来源：{path.name}\n"
        f"课程：{course_name}\n"
        "识别结果：\n"
        f"当前为 mock 视觉识别模式，系统已把图片《{stem}》作为多模态课件入库。"
        "正式识别数学公式、流程图、C++ 代码截图或物理电路图时，请配置 "
        "OCR_LLM_PROVIDER=ollama 并启动 qwen3-vl 等视觉模型。"
    )
