import io

from app.services.llm_service import get_llm_service


def extract_text(filename: str, content: bytes) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
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
