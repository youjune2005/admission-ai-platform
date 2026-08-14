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
    # 스캔 PDF OCR 폴백(Vision) 전용. 일반 대화/요약은 openai_model을 유지합니다.
    openai_ocr_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-small"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-3-5-sonnet-latest"

    # 네이버 클라우드 CLOVA General OCR (로컬 OCR 결과가 빈약할 때 사용)
    # 콘솔에서 General OCR 도메인 생성 → API Gateway 연동 후 Invoke URL / Secret 입력
    clova_ocr_invoke_url: str | None = None
    clova_ocr_secret: str | None = None
    clova_ocr_enable_table: bool = True

    # 로컬 OCR 엔진: rapidocr(ONNX Runtime) | paddle
    # 같은 PP-OCRv4 한국어 모델이지만 ONNX Runtime 쪽이 CPU에서 4~5배 빠릅니다.
    ocr_local_engine: str = "rapidocr"
    # 페이지를 몇 장씩 동시에 인식할지. 워커마다 엔진이 떠서 메모리도 함께 늘어납니다.
    # 두 엔진 모두 한 페이지에 코어를 다 쓰므로, 코어가 남는 서버에서만 올리세요.
    ocr_workers: int = 1
    # 아래 세 개는 paddle 엔진에서만 씁니다.
    ocr_paddle_cpu_threads: int = 10
    # macOS 휠에는 oneDNN이 빠져 있어 켜면 초기화가 깨집니다. 리눅스 배포 시에만 true.
    ocr_paddle_mkldnn: bool = False
    # 180° 뒤집힌 줄을 잡아주는 분류기. 살짝 기운(수 도) 문서는 검출 단계가 처리합니다.
    ocr_use_angle_cls: bool = False
    # PDF → 이미지 확대 배율. 낮추면 빨라지지만 작은 글자 인식률이 떨어집니다.
    ocr_render_scale: float = 2.0

    data_dir: str = str(_BACKEND_DIR.parent / "data")
    rag_top_k: int = 4

    # 개발 기본값. 공유 시 CORS_ORIGINS 환경변수로 터널 URL 추가
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    # True면 모든 Origin 허용 (단기 데모 공유용). 운영에서는 False 유지
    cors_allow_all: bool = False

    # IP당 분당 요청 수 (0 = 비활성). AI 비용 폭탄·매크로 완화
    rate_limit_per_minute: int = 60

    upload_dir: str = str(_BACKEND_DIR / "uploads")

    # macOS 한컴오피스 한글 UI 자동화로 HWP→PDF (요금 없음).
    # 접근성(Accessibility) 권한이 필요하며, 실패 시 LibreOffice/구조보존 폴백으로 이어집니다.
    # 설정: ./scripts/setup_hancom_hwp_pdf.sh
    hwp_use_hancom_ui: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    """테스트/재로드용. 서버 재시작 없이도 설정 캐시를 비울 수 있습니다."""
    get_settings.cache_clear()
