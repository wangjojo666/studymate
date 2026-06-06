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


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "StudyMate")
    api_prefix: str = os.getenv("API_PREFIX", "/api")
    database_url: str = _sqlite_url()
    storage_dir: Path = _path_from_env("STORAGE_DIR", BASE_DIR / "storage")
    upload_dir: Path = _path_from_env("UPLOAD_DIR", BASE_DIR / "storage" / "uploads")
    cors_origins: tuple[str, ...] = (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:5174",
        "http://localhost:5174",
    )

    llm_provider: str = os.getenv("LLM_PROVIDER", "ollama").lower()
    llm_model: str = os.getenv("LLM_MODEL", "qwen3-vl:30b")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "http://127.0.0.1:11434")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    ocr_default_max_pages: int = int(os.getenv("OCR_DEFAULT_MAX_PAGES", "10"))
    ocr_max_pages_per_request: int = int(os.getenv("OCR_MAX_PAGES_PER_REQUEST", "50"))


settings = Settings()
