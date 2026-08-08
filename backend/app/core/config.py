from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# VS Code에서 main.py를 직접 실행해도 cwd와 무관하게 backend/.env 를 찾도록 절대경로 사용
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ENV_FILE = _BACKEND_DIR / ".env"


class Settings(BaseSettings):
    """Application settings, loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "입시행정 통합 지원 시스템 API"
    environment: str = "development"

    database_url: str = f"sqlite:///{_BACKEND_DIR / 'admission_ai.db'}"

    llm_provider: str = "openai"  # "openai" | "anthropic" | "mock"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-3-5-sonnet-latest"

    data_dir: str = str(_BACKEND_DIR.parent / "data")
    rag_top_k: int = 4

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    upload_dir: str = str(_BACKEND_DIR / "uploads")


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    """테스트/재로드용. 서버 재시작 없이도 설정 캐시를 비울 수 있습니다."""
    get_settings.cache_clear()
