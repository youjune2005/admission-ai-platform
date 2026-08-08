"""FastAPI 엔트리포인트.

VS Code에서 main.py를 직접 실행(▶ Run)해도 동작하도록,
backend/ 디렉터리를 PYTHONPATH에 먼저 추가합니다.

권장 실행 방법 (터미널):
  cd backend && source .venv/bin/activate
  uvicorn app.main:app --reload
"""

from __future__ import annotations

import sys
from pathlib import Path

# VS Code ▶ Run / `python app/main.py` 로 직접 실행할 때
# `from app....` 임포트가 동작하도록 backend 루트를 path에 추가
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import analytics, chat, documents, workflow
from app.core.config import get_settings
from app.db.database import init_db

settings = get_settings()

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/")
def root():
    """브라우저에서 :8000 으로 들어왔을 때 Not Found 대신 안내를 보여줍니다.
    실제 UI는 프론트엔드(Vite) http://localhost:5173 입니다.
    """
    return {
        "message": "입시행정 통합 지원 시스템 API 서버입니다.",
        "ui": "http://localhost:5173",
        "docs": "http://127.0.0.1:8000/docs",
        "health": "http://127.0.0.1:8000/api/health",
    }


@app.get("/api/health")
def health_check():
    from app.services.llm_service import get_llm_service

    llm = get_llm_service()
    return {
        "status": "ok",
        "app": settings.app_name,
        "llm_provider": llm.provider,  # 실제 사용 중인 provider (키 없으면 mock)
        "configured_provider": settings.llm_provider,
        "openai_key_loaded": bool(settings.openai_api_key),
    }


app.include_router(chat.router)
app.include_router(analytics.router)
app.include_router(workflow.router)
app.include_router(documents.router)


if __name__ == "__main__":
    import uvicorn

    # 직접 실행 시: python app/main.py 또는 VS Code ▶ Run
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
