"""업로드 직전 자료명 추천.

전체 OCR/인덱싱은 하지 않고, 파일에서 앞부분 텍스트만 빠르게 읽어
짧은 LLM 호출로 문서 제목을 뽑습니다. 실패·지연 시 파일명 stem으로 폴백합니다.
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from app.services.hwp_convert_service import is_hwp_filename, peek_hwp_text
from app.services.llm_service import get_llm_service

logger = logging.getLogger(__name__)

TITLE_SNIPPET_LIMIT = 1600
TITLE_MAX_LEN = 80


def suggest_document_title(filename: str, content: bytes) -> str:
    """파일 내용 기반으로 자료명을 추천합니다. 항상 빈 문자열이 아닌 값을 돌려줍니다."""
    fallback = Path(filename or "document").stem.strip() or "자료"
    snippet = peek_document_text(filename, content, limit=TITLE_SNIPPET_LIMIT)
    if not snippet.strip():
        return fallback

    # 휴리스틱만으로도 분명한 제목이 보이면 LLM을 생략합니다(지연 최소화).
    heuristic = _heuristic_title(snippet, fallback)
    if heuristic and _looks_like_title(heuristic):
        # 아주 짧은 스니펫이거나 첫 줄이 뚜렷하면 LLM 생략
        first = _first_meaningful_line(snippet)
        if first and first == heuristic and len(snippet) < 400:
            return _clean_title(heuristic, fallback)

    title = _llm_title(snippet, filename=filename, fallback=fallback)
    return _clean_title(title, fallback)


def peek_document_text(filename: str, content: bytes, *, limit: int = TITLE_SNIPPET_LIMIT) -> str:
    """형식별 초고속 텍스트 미리보기(OCR 없음)."""
    lower = (filename or "").lower()
    try:
        if lower.endswith(".pdf"):
            text = _peek_pdf(content)
        elif lower.endswith(".docx"):
            text = _peek_docx(content)
        elif lower.endswith((".xlsx", ".xls", ".csv")):
            text = _peek_spreadsheet(filename, content)
        elif is_hwp_filename(filename):
            text = peek_hwp_text(filename, content, limit=limit)
        else:
            text = content.decode("utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        logger.exception("제목용 텍스트 미리보기 실패: %s", filename)
        return ""
    return _clip(text, limit)


def _peek_pdf(content: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    parts: list[str] = []
    for page in reader.pages[:2]:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def _peek_docx(content: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            xml = archive.read("word/document.xml")
    except Exception:  # noqa: BLE001
        return ""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return ""
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for para in root.iter(f"{{{ns['w']}}}p"):
        texts = [
            node.text or ""
            for node in para.iter(f"{{{ns['w']}}}t")
            if node.text
        ]
        line = "".join(texts).strip()
        if line:
            paragraphs.append(line)
        if len(paragraphs) >= 40:
            break
    return "\n".join(paragraphs)


def _peek_spreadsheet(filename: str, content: bytes) -> str:
    import pandas as pd

    lower = filename.lower()
    try:
        if lower.endswith(".csv"):
            frame = pd.read_csv(io.BytesIO(content), nrows=15)
            return frame.to_csv(index=False)
        sheets = pd.read_excel(io.BytesIO(content), sheet_name=None, nrows=10)
    except Exception:  # noqa: BLE001
        return ""
    blocks: list[str] = []
    for name, frame in list(sheets.items())[:3]:
        blocks.append(f"[시트] {name}")
        blocks.append(frame.fillna("").astype(str).to_csv(index=False))
    return "\n".join(blocks)


def _llm_title(snippet: str, *, filename: str, fallback: str) -> str:
    llm = get_llm_service()
    if llm.provider == "mock":
        return _heuristic_title(snippet, fallback) or fallback

    prompt = (
        "대학 입학·행정 문서의 공식 제목만 한 줄로 뽑으세요.\n"
        "규칙:\n"
        "- 제목만 출력(따옴표·설명·접두어 금지)\n"
        "- 80자 이내, 파일 확장자 붙이지 말 것\n"
        "- 문서 안의 표제·회의명·요강명을 우선하고, 없으면 내용을 요약해 짧은 제목으로\n"
        "- 근거가 없으면 파일명 stem을 그대로 사용\n\n"
        f"파일명: {filename}\n"
        f"폴백: {fallback}\n"
        f"--- 본문 앞부분 ---\n{snippet}"
    )
    try:
        raw = (llm.chat([{"role": "user", "content": prompt}]) or "").strip()
    except Exception:  # noqa: BLE001
        logger.exception("제목 LLM 호출 실패: %s", filename)
        return _heuristic_title(snippet, fallback) or fallback

    if not raw or raw.startswith("[AI 응답 실패]"):
        return _heuristic_title(snippet, fallback) or fallback
    # 모델이 여러 줄로 답하면 첫 줄만
    line = raw.splitlines()[0].strip().strip("\"'`")
    return line or fallback


def _heuristic_title(snippet: str, fallback: str) -> str:
    line = _first_meaningful_line(snippet)
    return line or fallback


def _first_meaningful_line(snippet: str) -> str | None:
    for raw in (snippet or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        # 페이지 번호·목차 기호 등 스킵
        if re.fullmatch(r"[\d./\-]+", line):
            continue
        if re.match(r"^(일시|장소|참석|배석|안건|기록|작성|번호|구분)\s*[:：]", line):
            continue
        # 조문·별표 코드만 있는 줄은 제목이 아닙니다.
        if re.fullmatch(r"[\d\-~\.～\s]+", line):
            continue
        hangul = len(re.findall(r"[가-힣]", line))
        if hangul < 2 and len(line) < 12:
            continue
        if len(line) < 4:
            continue
        # 너무 긴 줄은 제목이 아닐 가능성이 큽니다.
        if len(line) > TITLE_MAX_LEN:
            # 문장 구분자 앞에서 자르기
            cut = re.split(r"[\.。!?]|  ", line, maxsplit=1)[0].strip()
            line = (cut or line)[:TITLE_MAX_LEN].rstrip()
        return line
    return None


def _looks_like_title(text: str) -> bool:
    if not text or len(text) > TITLE_MAX_LEN:
        return False
    hangul = len(re.findall(r"[가-힣]", text))
    # 일시·장소 같은 메타 줄은 제목으로 쓰지 않습니다.
    if re.match(r"^(일시|장소|참석|배석|안건|기록|작성)\s*[:：]", text):
        return False
    return hangul >= 2 or len(text) >= 8


def _clean_title(title: str, fallback: str) -> str:
    cleaned = re.sub(r"\s+", " ", (title or "").strip())
    cleaned = cleaned.strip("\"'`")
    # 개정 이력·괄호 꼬리 제거(잘린 태그 포함)
    cleaned = re.sub(r"\s*<개정[^>]*>?\s*", " ", cleaned).strip()
    cleaned = re.sub(r"\s*<개정.*$", "", cleaned).strip()
    cleaned = re.sub(r"^\[별표\s*\d+\]\s*", "", cleaned).strip()
    # 확장자가 붙었으면 제거
    cleaned = re.sub(
        r"\.(pdf|hwp|hwpx|docx|xlsx|xls|txt|md)$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()
    if not cleaned:
        return fallback
    if len(cleaned) > TITLE_MAX_LEN:
        cleaned = cleaned[:TITLE_MAX_LEN].rstrip()
    return cleaned


def _clip(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"
