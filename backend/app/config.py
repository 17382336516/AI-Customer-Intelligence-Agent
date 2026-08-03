from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv() -> None:
    candidates = (Path.cwd() / ".env", Path.cwd().parent / ".env")
    for path in candidates:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)


_load_dotenv()


def _csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "8000"))
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/app.db")
    upload_dir: Path = Path(os.getenv("UPLOAD_DIR", "./data/uploads"))
    knowledge_dir: Path = Path(os.getenv("KNOWLEDGE_DIR", "./data/knowledge"))
    cors_origins: tuple[str, ...] = _csv(
        os.getenv("CORS_ORIGINS", "http://localhost:5173")
    )
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "").rstrip("/")
    llm_model: str = os.getenv("LLM_MODEL", "")
    llm_timeout_seconds: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "45"))
    llm_enhance_insights: bool = os.getenv("LLM_ENHANCE_INSIGHTS", "false").lower() == "true"
    llm_enhance_strategy: bool = os.getenv("LLM_ENHANCE_STRATEGY", "false").lower() == "true"
    min_analyzable_rows: int = int(os.getenv("MIN_ANALYZABLE_ROWS", "20"))
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "25"))
    default_cluster_count: int = int(os.getenv("DEFAULT_CLUSTER_COUNT", "4"))

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key and self.llm_base_url and self.llm_model)

    def ensure_directories(self) -> None:
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        if self.database_url.startswith("sqlite:///"):
            db_path = Path(self.database_url.removeprefix("sqlite:///"))
            db_path.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
