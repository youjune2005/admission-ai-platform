import base64
import io
import logging

from app.core.config import get_settings
from app.services.llm_service import get_llm_service

logger = logging.getLogger(__name__)

OCR_MIN_CHARS_PER_PAGE = 100
OCR_MAX_PAGES = 20


def _extract_pdf_text(content: bytes) -> tuple[str, int]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return text, len(reader.pages)


def _ocr_pdf_with_vision(filename: str, content: bytes) -> str:
    """스캔 PDF를 이미지로 렌더링하고 표 구조를 Markdown으로 복원합니다."""
    import pymupdf
    from openai import OpenAI

    settings = get_settings()
    if not settings.openai_api_key:
        return ""

    document = pymupdf.open(stream=content, filetype="pdf")
    client = OpenAI(api_key=settings.openai_api_key)
    pages: list[str] = []

    for page_index, page in enumerate(document[:OCR_MAX_PAGES]):
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2.5, 2.5), alpha=False)
        header_clip = pymupdf.Rect(
            page.rect.x0,
            page.rect.y0,
            page.rect.x1,
            page.rect.y0 + page.rect.height * 0.55,
        )
        header_pixmap = page.get_pixmap(
            matrix=pymupdf.Matrix(4, 4),
            clip=header_clip,
            alpha=False,
        )
        image_base64 = base64.b64encode(pixmap.tobytes("png")).decode("ascii")
        header_base64 = base64.b64encode(header_pixmap.tobytes("png")).decode("ascii")
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "당신은 한국어 행정문서 OCR 및 표 구조 추출 전문가입니다. "
                        "보이는 내용만 전사하고 읽을 수 없는 값을 추측하지 마세요."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"'{filename}' {page_index + 1}페이지를 OCR하세요. "
                                "첫 이미지는 전체 페이지이고 두 번째 이미지는 표 머리글 확대본입니다. "
                                "제목, 단위, 주석을 보존하고 표는 열 순서와 다단 헤더를 유지한 "
                                "Markdown 표로 변환하세요. 다단 헤더는 "
                                "'상위 헤더/하위 헤더' 형식의 단일 열로 평탄화하고 상위 헤더를 "
                                "별도 열로 중복 생성하지 마세요. 빈 입력칸은 '{{입력}}'으로 표시하고, "
                                "병합된 소계·합계·총계 행을 명시하세요. 코드 펜스 없이 결과만 출력하세요."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_base64}",
                                "detail": "high",
                            },
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{header_base64}",
                                "detail": "high",
                            },
                        },
                    ],
                },
            ],
        )
        page_text = response.choices[0].message.content or ""
        pages.append(f"## 페이지 {page_index + 1}\n\n{page_text}")

    if len(document) > OCR_MAX_PAGES:
        pages.append(
            f"\n> OCR 처리 제한으로 전체 {len(document)}페이지 중 "
            f"{OCR_MAX_PAGES}페이지만 처리했습니다."
        )
    return "\n\n".join(pages)


def extract_text(filename: str, content: bytes) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        embedded_text, page_count = _extract_pdf_text(content)
        meaningful_chars = len("".join(embedded_text.split()))
        if meaningful_chars >= page_count * OCR_MIN_CHARS_PER_PAGE:
            return embedded_text
        try:
            ocr_text = _ocr_pdf_with_vision(filename, content)
            return ocr_text or embedded_text
        except Exception:  # noqa: BLE001
            logger.exception("스캔 PDF OCR 실패: %s", filename)
            return embedded_text
    if lower.endswith((".csv", ".xlsx", ".xls")):
        return "(표 형식 파일은 분석(Analytics) 메뉴에서 처리해주세요)"
    try:
        return content.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def summarize_document(filename: str, text: str) -> str:
    llm = get_llm_service()
    trimmed = text[:8000]
    prompt = (
        f"다음은 '{filename}' 서류의 내용입니다. 입시행정 담당자가 빠르게 검토할 수 있도록 "
        "핵심 내용, 확인이 필요한 항목, 누락되었을 수 있는 정보를 한국어로 간결하게 요약해줘.\n\n"
        f"--- 서류 내용 ---\n{trimmed}"
    )
    return llm.chat([{"role": "user", "content": prompt}])
