from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from app.config import settings


PROVIDER_DEFAULTS = {
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini", "OPENAI_API_KEY"),
    "deepseek": ("https://api.deepseek.com", "deepseek-v4-flash", "DEEPSEEK_API_KEY"),
    "qwen": ("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus", "DASHSCOPE_API_KEY"),
    "zhipu": ("https://open.bigmodel.cn/api/paas/v4", "glm-4-flash", "ZHIPU_API_KEY"),
}


@dataclass(frozen=True)
class LlmResponse:
    content: str
    used_provider: str


@dataclass(frozen=True)
class LlmConfig:
    provider: str
    model: str
    base_url: str
    api_key: str


def call_llm(messages: list[dict[str, str]], temperature: float = 0.2) -> LlmResponse | None:
    primary = LlmConfig(
        provider=settings.text_llm_provider,
        model=settings.text_llm_model,
        base_url=settings.text_llm_base_url,
        api_key=settings.text_llm_api_key,
    )
    response = _call_provider(primary, messages, temperature)
    if response:
        return response

    fallback = LlmConfig(
        provider=settings.text_llm_fallback_provider,
        model=settings.text_llm_fallback_model,
        base_url=settings.text_llm_fallback_base_url,
        api_key=settings.text_llm_fallback_api_key,
    )
    if fallback.provider and fallback.provider != "none" and fallback != primary:
        return _call_provider(fallback, messages, temperature)
    return None


def _call_provider(
    config: LlmConfig, messages: list[dict[str, str]], temperature: float
) -> LlmResponse | None:
    provider = config.provider
    if provider == "mock":
        return None
    if provider == "ollama":
        return _call_ollama(config, messages, temperature)

    default_base, default_model, key_name = PROVIDER_DEFAULTS.get(
        provider, ("", "gpt-4o-mini", "LLM_API_KEY")
    )
    base_url = (config.base_url or default_base).rstrip("/")
    model = config.model or default_model
    api_key = config.api_key or os.getenv(key_name, "")
    allow_no_key = provider in {"custom", "openai_compatible", "local_openai"}
    if not base_url or (not api_key and not allow_no_key):
        return None

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None

    try:
        content = body["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, AttributeError):
        return None
    return LlmResponse(content=content, used_provider=f"{provider}/{model}")


def _call_ollama(
    config: LlmConfig, messages: list[dict[str, str]], temperature: float
) -> LlmResponse | None:
    base_url = (config.base_url or "http://127.0.0.1:11434").rstrip("/")
    model = config.model or "qwen3-vl:30b"
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    request = urllib.request.Request(
        f"{base_url}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None

    content = (body.get("message") or {}).get("content", "").strip()
    if not content:
        return None
    return LlmResponse(content=content, used_provider=f"ollama/{model}")


def offline_answer(question: str, context: str) -> str:
    if not context.strip():
        return "当前课程还没有可检索的资料。请先上传课程 PDF、PPT、Word 或 TXT。"
    sentences = _rank_sentences(question, context)
    if not sentences:
        sentences = [context[:260].strip()]
    bullets = "\n".join(f"{index}. {sentence}" for index, sentence in enumerate(sentences[:4], start=1))
    return (
        "根据已上传课程资料，和问题最相关的内容如下：\n"
        f"{bullets}\n\n"
        "建议你结合下方来源页码回到原文复核。"
    )


def offline_outline(context: str) -> str:
    if not context.strip():
        return "当前课程还没有可用于生成复习提纲的资料。"
    sentences = _split_sentences(context)[:12]
    concept_lines = "\n".join(f"- {item}" for item in sentences[:4]) or "- 暂无足够内容"
    formula_lines = "\n".join(
        f"- {item}" for item in sentences if any(symbol in item for symbol in ("=", "公式", "定理", "性质"))
    )
    if not formula_lines:
        formula_lines = "- 从资料中未识别到明显公式，可在上传更多讲义后重新生成。"
    mistake_lines = "\n".join(f"- 容易混淆：{item}" for item in sentences[4:8]) or "- 暂无足够内容"
    exam_lines = "\n".join(f"- 可考查：解释或应用“{item[:40]}”" for item in sentences[8:12]) or "- 暂无足够内容"
    return (
        "## 核心概念\n"
        f"{concept_lines}\n\n"
        "## 重点公式/结论\n"
        f"{formula_lines}\n\n"
        "## 易错点\n"
        f"{mistake_lines}\n\n"
        "## 可能考法\n"
        f"{exam_lines}"
    )


def offline_practice(context: str, count: int) -> str:
    if not context.strip():
        return "当前课程还没有可用于生成练习题的资料。"
    sentences = _split_sentences(context)
    if not sentences:
        sentences = [context[:120].strip()]
    question_types = ["选择题", "填空题", "简答题"]
    blocks: list[str] = []
    for index in range(count):
        basis = sentences[index % len(sentences)]
        qtype = question_types[index % len(question_types)]
        if qtype == "选择题":
            block = (
                f"{index + 1}. 【选择题】根据资料，下面哪一项最接近原文重点？\n"
                f"A. {basis[:46]}\nB. 与课程资料无关的说法\nC. 只记结论不需要理解条件\nD. 与原文相反的表述\n"
                f"答案：A\n解析：题干依据资料片段“{basis[:70]}”。"
            )
        elif qtype == "填空题":
            keyword = _first_keyword(basis)
            block = (
                f"{index + 1}. 【填空题】资料中强调的关键词之一是：____。\n"
                f"答案：{keyword}\n解析：该关键词来自资料片段“{basis[:70]}”。"
            )
        else:
            block = (
                f"{index + 1}. 【简答题】请简要说明以下知识点的含义或应用场景：{basis[:60]}\n"
                f"参考答案：应围绕资料中的核心表述展开，可概括为“{basis[:100]}”。"
            )
        blocks.append(block)
    return "\n\n".join(blocks)


def _rank_sentences(question: str, context: str) -> list[str]:
    q_terms = set(re.findall("[\u4e00-\u9fff]|[a-zA-Z0-9_]+", question.lower()))
    scored: list[tuple[int, str]] = []
    for sentence in _split_sentences(context):
        terms = set(re.findall("[\u4e00-\u9fff]|[a-zA-Z0-9_]+", sentence.lower()))
        score = len(q_terms & terms)
        if score > 0:
            scored.append((score, sentence))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [sentence for _, sentence in scored]


def _split_sentences(text: str) -> list[str]:
    pieces = re.split(r"(?<=[。！？.!?])\s+|\n+", text)
    return [piece.strip() for piece in pieces if len(piece.strip()) >= 8]


def _first_keyword(text: str) -> str:
    match = re.search("[\u4e00-\u9fff]{2,}|[a-zA-Z][a-zA-Z0-9_]{2,}", text)
    return match.group(0) if match else "核心概念"
