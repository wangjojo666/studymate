from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]

try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass


def _path_from_env(name: str, default: Path) -> Path:
    raw = os.getenv(name)
    path = Path(raw) if raw else default
    if not path.is_absolute():
        path = BASE_DIR / path
    return path


def _sqlite_url() -> str:
    configured = os.getenv("DATABASE_URL")
    if configured:
        if configured.startswith("sqlite:///./"):
            local = BASE_DIR / configured.replace("sqlite:///./", "", 1)
            return f"sqlite:///{local.as_posix()}"
        return configured
    return f"sqlite:///{(BASE_DIR / 'studymate.db').as_posix()}"


def _bool_from_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "StudyMate")
    app_env: str = os.getenv("APP_ENV", "development").lower()
    api_prefix: str = os.getenv("API_PREFIX", "/api")
    database_url: str = _sqlite_url()
    storage_dir: Path = _path_from_env("STORAGE_DIR", BASE_DIR / "storage")
    upload_dir: Path = _path_from_env("UPLOAD_DIR", BASE_DIR / "storage" / "uploads")
    chroma_dir: Path = _path_from_env("CHROMA_DIR", BASE_DIR / "storage" / "chroma")
    embedding_provider: str = os.getenv("EMBEDDING_PROVIDER", "hash").lower()
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
    embedding_base_url: str = os.getenv("EMBEDDING_BASE_URL", "")
    embedding_api_key: str = os.getenv("EMBEDDING_API_KEY", "")
    embedding_dimension: int = int(os.getenv("EMBEDDING_DIMENSION", "384"))
    embedding_batch_size: int = int(os.getenv("EMBEDDING_BATCH_SIZE", "16"))
    rag_top_k: int = int(os.getenv("RAG_TOP_K", "5"))
    rag_min_score: float = float(os.getenv("RAG_MIN_SCORE", "0.12"))
    rag_context_max_chars: int = int(os.getenv("RAG_CONTEXT_MAX_CHARS", "6000"))
    rag_enable_strict_source_mode: bool = _bool_from_env("RAG_ENABLE_STRICT_SOURCE_MODE", True)
    cors_origins: tuple[str, ...] = (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:5174",
        "http://localhost:5174",
    )

    # Backward-compatible generic LLM settings. New code should prefer
    # TEXT_LLM_* for RAG generation and OCR_LLM_* for vision OCR.
    llm_provider: str = os.getenv("LLM_PROVIDER", "mock").lower()
    llm_model: str = os.getenv("LLM_MODEL", "")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")

    text_llm_provider: str = os.getenv("TEXT_LLM_PROVIDER", os.getenv("LLM_PROVIDER", "mock")).lower()
    text_llm_model: str = os.getenv("TEXT_LLM_MODEL", os.getenv("LLM_MODEL", ""))
    text_llm_base_url: str = os.getenv("TEXT_LLM_BASE_URL", os.getenv("LLM_BASE_URL", ""))
    text_llm_api_key: str = os.getenv("TEXT_LLM_API_KEY", os.getenv("LLM_API_KEY", ""))
    text_llm_fallback_provider: str = os.getenv("TEXT_LLM_FALLBACK_PROVIDER", "none").lower()
    text_llm_fallback_model: str = os.getenv("TEXT_LLM_FALLBACK_MODEL", "")
    text_llm_fallback_base_url: str = os.getenv("TEXT_LLM_FALLBACK_BASE_URL", "")
    text_llm_fallback_api_key: str = os.getenv("TEXT_LLM_FALLBACK_API_KEY", "")

    ocr_llm_provider: str = os.getenv("OCR_LLM_PROVIDER", "ollama").lower()
    ocr_llm_model: str = os.getenv("OCR_LLM_MODEL", os.getenv("LLM_MODEL", "qwen3-vl:30b"))
    ocr_llm_base_url: str = os.getenv(
        "OCR_LLM_BASE_URL", os.getenv("LLM_BASE_URL", "http://127.0.0.1:11434")
    )
    ocr_default_max_pages: int = int(os.getenv("OCR_DEFAULT_MAX_PAGES", "10"))
    ocr_max_pages_per_request: int = int(os.getenv("OCR_MAX_PAGES_PER_REQUEST", "20"))
    document_upload_max_bytes: int = int(os.getenv("DOCUMENT_UPLOAD_MAX_BYTES", str(100 * 1024 * 1024)))
    txt_upload_max_bytes: int = int(os.getenv("TXT_UPLOAD_MAX_BYTES", str(10 * 1024 * 1024)))
    auth_secret_key: str = os.getenv("AUTH_SECRET_KEY", "studymate-dev-secret-change-me")
    auth_token_expire_minutes: int = int(os.getenv("AUTH_TOKEN_EXPIRE_MINUTES", str(60 * 24 * 7)))
    demo_user_email: str = os.getenv("DEMO_USER_EMAIL", "demo@studymate.local")
    demo_user_password: str = os.getenv("DEMO_USER_PASSWORD", "studymate-demo")
    cpp_run_enabled: bool = _bool_from_env("CPP_RUN_ENABLED", False)
    cpp_compile_timeout_seconds: int = int(os.getenv("CPP_COMPILE_TIMEOUT_SECONDS", "8"))
    cpp_run_timeout_seconds: int = int(os.getenv("CPP_RUN_TIMEOUT_SECONDS", "5"))


settings = Settings()


def validate_runtime_settings() -> None:
    if settings.app_env == "production" and settings.auth_secret_key == "studymate-dev-secret-change-me":
        raise RuntimeError("APP_ENV=production 时必须修改 AUTH_SECRET_KEY，不能使用默认开发密钥。")
