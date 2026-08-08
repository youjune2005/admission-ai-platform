from fastapi import APIRouter, File, HTTPException, UploadFile

from app.schemas.analytics import AnalyticsResult
from app.services.analytics_service import analyze_file

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

ALLOWED_EXTENSIONS = (".csv", ".xlsx", ".xls")


@router.post("/upload", response_model=AnalyticsResult)
async def upload_and_analyze(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(status_code=400, detail="CSV 또는 Excel 파일만 업로드할 수 있습니다.")

    content = await file.read()
    try:
        return analyze_file(file.filename, content)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"파일을 분석하는 중 오류가 발생했습니다: {exc}") from exc
