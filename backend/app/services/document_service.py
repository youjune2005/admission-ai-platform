import base64
import io
import logging
import re
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from app.core.config import get_settings
from app.services.llm_service import get_llm_service

logger = logging.getLogger(__name__)

OCR_MIN_CHARS_PER_PAGE = 80
OCR_MAX_PAGES = 20
OCR_MAX_RETRIES = 10
OCR_PAGE_GAP_SEC = 0.75
DOCX_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

_ocr_local = threading.local()
_ocr_init_lock = threading.Lock()
_ocr_pool_lock = threading.Lock()
_ocr_pool: ThreadPoolExecutor | None = None
_local_ocr_failed = False


@dataclass
class ExtractionResult:
    """추출된 본문과 그 품질 정보.

    mode:
      native — PDF 임베디드 텍스트
      ocr — 로컬 OCR(RapidOCR/PaddleOCR)
      ocr_clova — 로컬 OCR 결과가 빈약해 CLOVA OCR로 재시도
      ocr_vision — 앞선 OCR이 빈약해 GPT Vision(OCR 전용 모델)으로 재시도
      llm_recovered — OCR 실패 후 LLM 정리
      empty — 추출 실패
    """

    text: str
    mode: str = "native"
    warning: str | None = None

    @property
    def degraded(self) -> bool:
        return self.mode == "llm_recovered"


def _extract_pdf_text(content: bytes) -> tuple[str, int]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return text, len(reader.pages)


def _retry_wait_seconds(exc: Exception, attempt: int) -> float:
    """OpenAI 429 메시지·지수 백오프로 대기 시간을 계산합니다."""
    message = str(exc)
    match = re.search(r"try again in ([\d.]+)\s*(ms|s)", message, re.IGNORECASE)
    if match:
        value = float(match.group(1))
        wait = value / 1000.0 if match.group(2).lower() == "ms" else value
        return max(0.5, min(wait + 0.35, 45.0))
    return min(45.0, (2**attempt) * 0.6)


def _openai_vision_client():
    import httpx
    from openai import OpenAI

    settings = get_settings()
    return OpenAI(
        api_key=settings.openai_api_key,
        http_client=httpx.Client(trust_env=False, timeout=120.0),
    )


def _chat_completion_with_retry(client, *, model: str, messages: list) -> str:
    """분당 토큰 한도(429) 등에 걸리면 잠시 대기 후 재요청합니다."""
    from openai import APIConnectionError, APITimeoutError, RateLimitError

    last_error: Exception | None = None
    for attempt in range(OCR_MAX_RETRIES):
        try:
            response = client.chat.completions.create(model=model, messages=messages)
            return response.choices[0].message.content or ""
        except RateLimitError as exc:
            last_error = exc
            wait = _retry_wait_seconds(exc, attempt)
            logger.warning(
                "OCR rate limit (시도 %s/%s) — %.1f초 후 재시도: %s",
                attempt + 1,
                OCR_MAX_RETRIES,
                wait,
                exc,
            )
            time.sleep(wait)
        except (APIConnectionError, APITimeoutError) as exc:
            last_error = exc
            wait = min(20.0, (2**attempt) * 0.8)
            logger.warning(
                "OCR 네트워크 오류 (시도 %s/%s) — %.1f초 후 재시도: %s",
                attempt + 1,
                OCR_MAX_RETRIES,
                wait,
                exc,
            )
            time.sleep(wait)
    if last_error is not None:
        raise last_error
    return ""


def _meaningful_len(text: str) -> int:
    return len("".join((text or "").split()))


def _ocr_is_weak(text: str, page_count: int) -> bool:
    """페이지당 의미 있는 글자 수가 기준 미만이면 빈약한 OCR로 봅니다."""
    return _meaningful_len(text) < max(page_count, 1) * OCR_MIN_CHARS_PER_PAGE


def _local_engine_name() -> str:
    return (get_settings().ocr_local_engine or "rapidocr").strip().lower()


def _local_ocr_available() -> bool:
    """엔진을 올리지 않고 설치 여부만 봅니다(메모리는 워커 스레드에서만 씁니다)."""
    global _local_ocr_failed
    if _local_ocr_failed:
        return False
    module = "paddleocr" if _local_engine_name() == "paddle" else "rapidocr"
    try:
        __import__(module)
    except Exception as exc:  # noqa: BLE001
        _local_ocr_failed = True
        logger.warning(
            "로컬 OCR(%s)을 불러올 수 없습니다. 스캔 PDF는 CLOVA/GPT Vision OCR로 처리합니다: %s",
            module,
            exc,
        )
        return False
    return True


def _get_ocr_pool() -> ThreadPoolExecutor:
    """페이지 인식용 스레드 풀. 엔진을 계속 물고 있으려고 재사용합니다.

    문서마다 풀을 새로 만들면 스레드가 바뀌어 매번 모델을 다시 올리게 됩니다.
    """
    global _ocr_pool
    if _ocr_pool is None:
        with _ocr_pool_lock:
            if _ocr_pool is None:
                workers = max(1, get_settings().ocr_workers)
                _ocr_pool = ThreadPoolExecutor(
                    max_workers=workers, thread_name_prefix="local-ocr"
                )
    return _ocr_pool


def _get_rapidocr() -> Any | None:
    """RapidOCR(ONNX Runtime, 한국어 PP-OCRv4) 엔진을 스레드마다 준비합니다.

    PaddleOCR과 같은 모델을 쓰지만 추론 런타임이 달라 CPU에서 4~5배 빠릅니다.
    """
    global _local_ocr_failed
    engine = getattr(_ocr_local, "rapid", None)
    if engine is not None:
        return engine
    if _local_ocr_failed:
        return None

    with _ocr_init_lock:
        if _local_ocr_failed:
            return None
        try:
            from rapidocr import EngineType, LangRec, ModelType, OCRVersion, RapidOCR

            engine = RapidOCR(
                params={
                    "Rec.engine_type": EngineType.ONNXRUNTIME,
                    "Rec.lang_type": LangRec.KOREAN,
                    "Rec.model_type": ModelType.MOBILE,
                    "Rec.ocr_version": OCRVersion.PPOCRV4,
                    "Global.use_cls": get_settings().ocr_use_angle_cls,
                }
            )
        except Exception as exc:  # noqa: BLE001
            _local_ocr_failed = True
            logger.warning("RapidOCR 초기화 실패 — 다음 OCR로 폴백합니다: %s", exc)
            return None
        _ocr_local.rapid = engine
        logger.info("RapidOCR(한국어 PP-OCRv4, ONNX Runtime) 엔진을 초기화했습니다.")
        return engine


def _ocr_page_with_rapidocr(image: Any, filename: str, page_no: int) -> list[str]:
    engine = _get_rapidocr()
    if engine is None:
        return []
    try:
        result = engine(image)
    except Exception:  # noqa: BLE001
        logger.exception("RapidOCR 페이지 실패: %s p%s", filename, page_no)
        return []
    texts = getattr(result, "txts", None) or []
    return [str(text).strip() for text in texts if str(text).strip()]


def _get_paddle_ocr() -> Any | None:
    """스레드마다 PaddleOCR 엔진을 하나씩 준비합니다.

    Paddle 추론기는 스레드 안전하지 않아 엔진 하나를 여러 스레드가 공유하면
    결과가 섞이거나 죽습니다. 페이지 병렬 처리를 위해 스레드별로 따로 만듭니다.
    미설치·호환 불가 시 None.
    """
    global _local_ocr_failed
    engine = getattr(_ocr_local, "paddle", None)
    if engine is not None:
        return engine
    if _local_ocr_failed:
        return None

    with _ocr_init_lock:
        if _local_ocr_failed:
            return None
        try:
            from paddleocr import PaddleOCR
        except Exception as exc:  # noqa: BLE001
            _local_ocr_failed = True
            logger.warning(
                "PaddleOCR을 불러올 수 없습니다(paddlepaddle 미설치 또는 Python 비호환). "
                "스캔 PDF는 CLOVA/GPT Vision OCR로 처리합니다: %s",
                exc,
            )
            return None

        settings = get_settings()
        kwargs: dict[str, Any] = {
            "lang": "korean",
            "use_angle_cls": settings.ocr_use_angle_cls,
            "cpu_threads": max(1, settings.ocr_paddle_cpu_threads),
            "rec_batch_num": 8,
        }
        if settings.ocr_paddle_mkldnn:
            kwargs["enable_mkldnn"] = True

        # 빌드·버전에 따라 못 받는 옵션이 있습니다(예: macOS 휠에는 oneDNN 없음).
        # 거절당하면 문제 될 만한 옵션부터 빼고 최소 구성까지 내려가며 재시도합니다.
        last_error: Exception | None = None
        for drop in ("", "enable_mkldnn", "rec_batch_num", "cpu_threads"):
            if drop:
                if drop not in kwargs:
                    continue
                kwargs.pop(drop, None)
            try:
                engine = PaddleOCR(**kwargs)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.info("PaddleOCR 옵션 적용 실패(%s) — 옵션을 줄여 재시도합니다.", exc)
                continue
            _ocr_local.paddle = engine
            logger.info("PaddleOCR(한국어) 엔진 초기화: %s", kwargs)
            return engine

        _local_ocr_failed = True
        logger.warning("PaddleOCR 초기화 실패 — 다음 OCR로 폴백합니다: %s", last_error)
        return None


def _parse_paddle_lines(result: Any) -> list[str]:
    """PaddleOCR 버전별 결과 형식을 텍스트 줄로 정규화합니다."""
    lines: list[str] = []
    if not result:
        return lines

    # 구 API: [ [ [box, (text, conf)], ... ] ]  또는 페이지당 한 리스트
    pages = result if isinstance(result, list) else [result]
    for page in pages:
        if page is None:
            continue
        if isinstance(page, dict):
            # 신 API 유사 구조
            rec_texts = page.get("rec_texts") or page.get("texts") or []
            for text in rec_texts:
                if text and str(text).strip():
                    lines.append(str(text).strip())
            continue
        if not isinstance(page, list):
            continue
        for item in page:
            try:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    payload = item[1]
                    if isinstance(payload, (list, tuple)) and payload:
                        text = str(payload[0]).strip()
                    else:
                        text = str(payload).strip()
                    if text:
                        lines.append(text)
            except Exception:  # noqa: BLE001
                continue
    return lines


def _ocr_page_with_paddle(image: Any, filename: str, page_no: int) -> list[str]:
    engine = _get_paddle_ocr()
    if engine is None:
        return []
    use_cls = get_settings().ocr_use_angle_cls
    try:
        raw = engine.ocr(image, cls=use_cls)
    except TypeError:
        # 일부 버전은 cls 인자를 받지 않습니다.
        try:
            raw = engine.ocr(image)
        except Exception:  # noqa: BLE001
            logger.exception("PaddleOCR 페이지 실패: %s p%s", filename, page_no)
            return []
    except Exception:  # noqa: BLE001
        logger.exception("PaddleOCR 페이지 실패: %s p%s", filename, page_no)
        return []
    return _parse_paddle_lines(raw)


def _ocr_page_local(image: Any, filename: str, page_no: int) -> list[str]:
    """페이지 이미지 한 장을 인식합니다. 실패해도 다른 페이지는 계속 갑니다."""
    if _local_engine_name() == "paddle":
        return _ocr_page_with_paddle(image, filename, page_no)
    return _ocr_page_with_rapidocr(image, filename, page_no)


def _ocr_pdf_locally(filename: str, content: bytes) -> str:
    """스캔 PDF를 로컬 OCR(기본 RapidOCR, 옵션 PaddleOCR)로 인식합니다.

    렌더링은 순차로 하고 인식만 스레드로 나눕니다. 한 번에 워커 수만큼만
    이미지를 만들어 메모리 사용량을 묶어 둡니다.
    """
    import numpy as np
    import pymupdf

    if not _local_ocr_available():
        return ""

    settings = get_settings()
    scale = max(1.0, settings.ocr_render_scale)
    document = pymupdf.open(stream=content, filetype="pdf")
    page_count = min(len(document), OCR_MAX_PAGES)
    pool = _get_ocr_pool()
    workers = max(1, min(settings.ocr_workers, page_count))
    pages: list[str] = []

    def render(page_index: int) -> Any:
        # RGB 픽셀 → numpy (H, W, 3). 두 엔진 모두 RGB 배열을 그대로 받습니다.
        pixmap = document[page_index].get_pixmap(
            matrix=pymupdf.Matrix(scale, scale), alpha=False
        )
        image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
            pixmap.height, pixmap.width, pixmap.n
        )
        return image[:, :, :3] if pixmap.n == 4 else image

    for start in range(0, page_count, workers):
        batch = list(range(start, min(start + workers, page_count)))
        logger.info(
            "%s 페이지 %s-%s/%s (워커 %s): %s",
            _local_engine_name(),
            batch[0] + 1,
            batch[-1] + 1,
            page_count,
            workers,
            filename,
        )
        futures = [
            pool.submit(_ocr_page_local, render(index), filename, index + 1)
            for index in batch
        ]
        for page_index, future in zip(batch, futures):
            lines = future.result()
            if lines:
                pages.append(f"## 페이지 {page_index + 1}\n\n" + "\n".join(lines))

    if len(document) > OCR_MAX_PAGES:
        pages.append(
            f"\n> OCR 처리 제한으로 전체 {len(document)}페이지 중 "
            f"{OCR_MAX_PAGES}페이지만 처리했습니다."
        )
    return "\n\n".join(pages)


def _clova_configured() -> bool:
    settings = get_settings()
    return bool((settings.clova_ocr_invoke_url or "").strip() and (settings.clova_ocr_secret or "").strip())


def _parse_clova_image_text(image: dict) -> str:
    """CLOVA General OCR 응답 한 장에서 본문·표를 텍스트로 합칩니다."""
    parts: list[str] = []

    tables = image.get("tables") or []
    for table_index, table in enumerate(tables, start=1):
        cells = table.get("cells") or []
        if not cells:
            infer = (table.get("inferText") or "").strip()
            if infer:
                parts.append(infer)
            continue
        grid: dict[tuple[int, int], str] = {}
        max_row = 0
        max_col = 0
        for cell in cells:
            row = int(cell.get("rowIndex") or 0)
            col = int(cell.get("columnIndex") or 0)
            max_row = max(max_row, row)
            max_col = max(max_col, col)
            cell_bits: list[str] = []
            for line in cell.get("cellTextLines") or []:
                for word in line.get("cellWords") or []:
                    t = (word.get("inferText") or "").strip()
                    if t:
                        cell_bits.append(t)
            if not cell_bits:
                t = (cell.get("inferText") or "").strip()
                if t:
                    cell_bits.append(t)
            text = " ".join(cell_bits).replace("|", "/")
            if text:
                grid[(row, col)] = text
        if not grid:
            continue
        lines = [f"### 표 {table_index}"]
        header = "| " + " | ".join(f"열{c + 1}" for c in range(max_col + 1)) + " |"
        sep = "| " + " | ".join("---" for _ in range(max_col + 1)) + " |"
        lines.append(header)
        lines.append(sep)
        for r in range(max_row + 1):
            row_cells = [grid.get((r, c), "") for c in range(max_col + 1)]
            lines.append("| " + " | ".join(row_cells) + " |")
        parts.append("\n".join(lines))

    field_line: list[str] = []
    for field in image.get("fields") or []:
        text = (field.get("inferText") or "").strip()
        if not text:
            continue
        field_line.append(text)
        if field.get("lineBreak"):
            parts.append(" ".join(field_line))
            field_line = []
    if field_line:
        parts.append(" ".join(field_line))

    return "\n".join(p for p in parts if p).strip()


def _ocr_pdf_with_clova(filename: str, content: bytes) -> str:
    """스캔 PDF를 CLOVA General OCR로 인식합니다. 키가 없으면 빈 문자열."""
    import uuid

    import httpx
    import pymupdf

    settings = get_settings()
    invoke_url = (settings.clova_ocr_invoke_url or "").strip()
    secret = (settings.clova_ocr_secret or "").strip()
    if not invoke_url or not secret:
        return ""

    document = pymupdf.open(stream=content, filetype="pdf")
    pages: list[str] = []
    page_count = min(len(document), OCR_MAX_PAGES)

    with httpx.Client(trust_env=False, timeout=90.0) as client:
        for page_index, page in enumerate(document[:OCR_MAX_PAGES]):
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2.0, 2.0), alpha=False)
            image_b64 = base64.b64encode(pixmap.tobytes("png")).decode("ascii")
            payload = {
                "version": "V2",
                "requestId": str(uuid.uuid4()),
                "timestamp": int(time.time() * 1000),
                "lang": "ko",
                "enableTableDetection": bool(settings.clova_ocr_enable_table),
                "images": [
                    {
                        "format": "png",
                        "name": f"{Path(filename).stem}_p{page_index + 1}",
                        "data": image_b64,
                    }
                ],
            }
            logger.info("CLOVA OCR 페이지 %s/%s: %s", page_index + 1, page_count, filename)
            try:
                response = client.post(
                    invoke_url,
                    headers={
                        "Content-Type": "application/json",
                        "X-OCR-SECRET": secret,
                    },
                    json=payload,
                )
                response.raise_for_status()
                body = response.json()
            except Exception:  # noqa: BLE001
                logger.exception("CLOVA OCR 페이지 실패: %s p%s", filename, page_index + 1)
                continue

            images = body.get("images") or []
            if not images:
                continue
            page_text = _parse_clova_image_text(images[0])
            if page_text:
                pages.append(f"## 페이지 {page_index + 1}\n\n{page_text}")

    if len(document) > OCR_MAX_PAGES:
        pages.append(
            f"\n> OCR 처리 제한으로 전체 {len(document)}페이지 중 "
            f"{OCR_MAX_PAGES}페이지만 처리했습니다."
        )
    return "\n\n".join(pages)


def _ocr_pdf_with_vision(filename: str, content: bytes) -> str:
    """스캔 PDF를 GPT Vision으로 재인식합니다. OCR 전용 모델(기본 gpt-4o)을 씁니다."""
    import pymupdf

    settings = get_settings()
    if not settings.openai_api_key:
        logger.warning("OpenAI API 키가 없어 Vision OCR을 건너뜁니다: %s", filename)
        return ""

    ocr_model = (settings.openai_ocr_model or "gpt-4o").strip() or "gpt-4o"
    document = pymupdf.open(stream=content, filetype="pdf")
    client = _openai_vision_client()
    pages: list[str] = []
    page_count = min(len(document), OCR_MAX_PAGES)

    for page_index, page in enumerate(document[:OCR_MAX_PAGES]):
        if page_index > 0:
            time.sleep(OCR_PAGE_GAP_SEC)

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
        logger.info(
            "Vision OCR(%s) 페이지 %s/%s: %s",
            ocr_model,
            page_index + 1,
            page_count,
            filename,
        )
        page_text = _chat_completion_with_retry(
            client,
            model=ocr_model,
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
        pages.append(f"## 페이지 {page_index + 1}\n\n{page_text}")

    if len(document) > OCR_MAX_PAGES:
        pages.append(
            f"\n> OCR 처리 제한으로 전체 {len(document)}페이지 중 "
            f"{OCR_MAX_PAGES}페이지만 처리했습니다."
        )
    return "\n\n".join(pages)


def _extract_docx_text(content: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            xml = archive.read("word/document.xml")
    except Exception:  # noqa: BLE001
        return ""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return ""
    paragraphs: list[str] = []
    for para in root.iter(f"{{{DOCX_NS['w']}}}p"):
        parts = [
            node.text or ""
            for node in para.iter(f"{{{DOCX_NS['w']}}}t")
            if node.text
        ]
        line = "".join(parts).strip()
        if line:
            paragraphs.append(line)
    return "\n".join(paragraphs)


def _extract_spreadsheet_text(filename: str, content: bytes) -> str:
    import pandas as pd

    lower = filename.lower()
    try:
        if lower.endswith(".csv"):
            frame = pd.read_csv(io.BytesIO(content))
            sheets = {"시트1": frame}
        else:
            sheets = pd.read_excel(io.BytesIO(content), sheet_name=None)
    except Exception:  # noqa: BLE001
        logger.exception("스프레드시트 텍스트 추출 실패: %s", filename)
        return ""

    blocks: list[str] = []
    for sheet_name, frame in sheets.items():
        cleaned = frame.fillna("").astype(str)
        if cleaned.empty:
            continue
        blocks.append(f"## {sheet_name}")
        blocks.append(cleaned.to_csv(index=False))
    return "\n\n".join(blocks).strip()


def _ai_recover_text(filename: str, raw_snippet: str) -> str:
    """PDF 등에서 추출된 깨진 텍스트를 LLM으로 정리합니다."""
    snippet = (raw_snippet or "").strip()
    if not snippet:
        return ""
    llm = get_llm_service()
    if llm.provider == "mock":
        return ""
    prompt = (
        f"다음은 '{filename}' 파일에서 기계적으로 추출한 깨진/불완전한 텍스트입니다. "
        "읽을 수 있는 한국어·숫자·표 내용만 정리해 복원하고, "
        "없는 내용은 만들지 마세요. 코드 펜스 없이 본문만 출력하세요.\n\n"
        f"--- 추출 원문 ---\n{snippet[:12000]}"
    )
    try:
        recovered = (llm.chat([{"role": "user", "content": prompt}]) or "").strip()
    except Exception:  # noqa: BLE001
        logger.exception("AI 텍스트 복원 실패: %s", filename)
        return ""
    if not recovered or recovered.startswith("[AI 응답 실패]"):
        return ""
    return recovered


def extract_document(filename: str, content: bytes) -> ExtractionResult:
    """파일에서 본문을 추출하고 어떤 경로로 추출했는지 함께 돌려줍니다."""
    lower = filename.lower()

    if lower.endswith(".pdf"):
        return _extract_pdf_document(filename, content)

    if lower.endswith(".docx"):
        text = _extract_docx_text(content)
    elif lower.endswith((".csv", ".xlsx", ".xls")):
        text = _extract_spreadsheet_text(filename, content)
    else:
        try:
            text = content.decode("utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            text = ""

    if not text.strip():
        return ExtractionResult("", mode="empty")
    return ExtractionResult(text)


def _extract_pdf_document(filename: str, content: bytes) -> ExtractionResult:
    """임베디드 → 로컬 OCR → CLOVA → GPT-4o Vision 순으로 추출합니다."""
    embedded_text, page_count = _extract_pdf_text(content)
    page_count = max(page_count, 1)
    if not _ocr_is_weak(embedded_text, page_count):
        return ExtractionResult(embedded_text)

    local_text = ""
    try:
        local_text = _ocr_pdf_locally(filename, content)
    except Exception:  # noqa: BLE001
        logger.exception("로컬 OCR 실패: %s", filename)

    if local_text.strip() and not _ocr_is_weak(local_text, page_count):
        return ExtractionResult(local_text, mode="ocr")

    clova_text = ""
    if _clova_configured():
        try:
            clova_text = _ocr_pdf_with_clova(filename, content)
        except Exception:  # noqa: BLE001
            logger.exception("CLOVA OCR 실패: %s", filename)
        if clova_text.strip() and not _ocr_is_weak(clova_text, page_count):
            return ExtractionResult(
                clova_text,
                mode="ocr_clova",
                warning=(
                    "로컬 OCR 결과가 빈약해 CLOVA OCR로 재인식했습니다. "
                    "표·숫자 정확도를 한 번 확인해 주세요."
                    if local_text.strip()
                    else None
                ),
            )
    else:
        logger.info(
            "CLOVA OCR 미설정(CLOVA_OCR_INVOKE_URL / CLOVA_OCR_SECRET) — Vision으로 폴백: %s",
            filename,
        )

    vision_text = ""
    try:
        vision_text = _ocr_pdf_with_vision(filename, content)
    except Exception:  # noqa: BLE001
        logger.exception("Vision OCR 실패: %s", filename)

    candidates = [
        ("ocr_vision", vision_text),
        ("ocr_clova", clova_text),
        ("ocr", local_text),
    ]
    best_mode, best_text = max(
        candidates,
        key=lambda item: _meaningful_len(item[1]),
    )
    if best_text.strip() and (
        not _ocr_is_weak(best_text, page_count)
        or _meaningful_len(best_text) > _meaningful_len(embedded_text)
    ):
        warning = None
        if best_mode == "ocr_vision" and (local_text.strip() or clova_text.strip()):
            warning = (
                "로컬/CLOVA OCR 결과가 빈약해 GPT Vision(OCR 전용 모델)으로 재인식했습니다. "
                "표·숫자 정확도를 한 번 확인해 주세요."
            )
        elif best_mode == "ocr_clova" and local_text.strip():
            warning = (
                "로컬 OCR 결과가 빈약해 CLOVA OCR로 재인식했습니다. "
                "표·숫자 정확도를 한 번 확인해 주세요."
            )
        return ExtractionResult(best_text, mode=best_mode, warning=warning)

    if embedded_text.strip():
        recovered = _ai_recover_text(filename, embedded_text)
        if recovered:
            return ExtractionResult(
                recovered,
                mode="llm_recovered",
                warning=(
                    "전용 OCR·CLOVA·Vision OCR이 충분하지 않아 AI가 깨진 텍스트를 정리한 결과로 "
                    "인덱싱했습니다. 원문과 다를 수 있으니 내용을 확인하고 "
                    "텍스트가 살아 있는 파일로 다시 올려 주세요."
                ),
            )
        return ExtractionResult(
            embedded_text,
            mode="llm_recovered",
            warning=(
                "OCR 품질이 낮은 상태로 인덱싱했습니다. "
                "내용을 확인하고 다시 업로드해 주세요."
            ),
        )

    return ExtractionResult("", mode="empty")


def extract_text(filename: str, content: bytes) -> str:
    """호환용 래퍼. 본문 텍스트만 필요할 때 사용합니다."""
    return extract_document(filename, content).text


def summarize_document(filename: str, text: str) -> str:
    llm = get_llm_service()
    trimmed = text[:8000]
    prompt = (
        f"다음은 '{filename}' 서류의 내용입니다. 입시행정 담당자가 빠르게 검토할 수 있도록 "
        "핵심 내용, 확인이 필요한 항목, 누락되었을 수 있는 정보를 한국어로 간결하게 요약해줘.\n\n"
        f"--- 서류 내용 ---\n{trimmed}"
    )
    return llm.chat([{"role": "user", "content": prompt}])
