"""HWP/HWPX → PDF 변환.

우선순위(모두 로컬·추가 요금 없음):
  1. macOS 한컴오피스 한글 UI 자동화(선택, 접근성 권한) — 원본 렌더링에 가장 가깝습니다.
  2. LibreOffice(soffice) 직접 변환.
  3. 구조 보존 폴백(HWP: pyhwp HTML, HWPX: 표·이미지 HTML) → LibreOffice PDF.
  4. 본문 텍스트만 뽑은 검색용 PDF.

변환된 PDF는 기존 추출·OCR·RAG 파이프라인에 그대로 넘깁니다.
"""

from __future__ import annotations

import io
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import zlib
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

# 한컴 UI는 GUI 세션을 점유하므로 동시에 하나만 돌립니다.
_HANCOM_UI_LOCK = threading.Lock()

_SOFFICE_CANDIDATES = (
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "/usr/local/bin/soffice",
    "/opt/homebrew/bin/soffice",
    "soffice",
    "libreoffice",
)

_HANCOM_APP = Path("/Applications/Hancom Office HWP.app")
_HANCOM_SCRIPT = (
    Path(__file__).resolve().parents[3] / "scripts" / "hancom_hwp_to_pdf.applescript"
)


def is_hwp_filename(filename: str) -> bool:
    lower = (filename or "").lower()
    return lower.endswith(".hwp") or lower.endswith(".hwpx")


def find_soffice() -> str | None:
    for candidate in _SOFFICE_CANDIDATES:
        if candidate in {"soffice", "libreoffice"}:
            path = shutil.which(candidate)
            if path:
                return path
            continue
        if Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def hancom_ui_available() -> bool:
    return _HANCOM_APP.is_dir() and _HANCOM_SCRIPT.is_file()


def convert_hwp_to_pdf(filename: str, content: bytes) -> bytes:
    """HWP/HWPX 바이트를 PDF 바이트로 바꿉니다. 실패 시 예외를 그대로 올립니다."""
    if not content:
        raise ValueError("빈 HWP 파일입니다.")

    from app.core.config import get_settings

    settings = get_settings()
    if settings.hwp_use_hancom_ui and hancom_ui_available() and sys.platform == "darwin":
        try:
            pdf = _convert_with_hancom_ui(filename, content)
            if pdf.startswith(b"%PDF"):
                logger.info(
                    "한컴 UI 자동화로 HWP→PDF 변환 완료: %s (%s bytes)",
                    filename,
                    len(pdf),
                )
                return pdf
        except Exception:  # noqa: BLE001
            logger.exception(
                "한컴 UI 자동화 실패(접근성 권한·UI 변경 가능) — 다음 경로로 폴백: %s",
                filename,
            )

    soffice = find_soffice()
    if soffice:
        try:
            pdf = _convert_with_libreoffice(soffice, filename, content)
            if pdf.startswith(b"%PDF"):
                logger.info("LibreOffice로 HWP→PDF 변환 완료: %s (%s bytes)", filename, len(pdf))
                return pdf
        except Exception:  # noqa: BLE001
            logger.exception("LibreOffice HWP 직접 변환 실패: %s", filename)

    lower = filename.lower()
    if soffice:
        try:
            if lower.endswith(".hwpx"):
                pdf = _convert_hwpx_structured(soffice, filename, content)
            else:
                pdf = _convert_hwp_structured(soffice, filename, content)
            if pdf.startswith(b"%PDF"):
                logger.info(
                    "구조 보존 경로로 HWP→PDF 변환 완료: %s (%s bytes)",
                    filename,
                    len(pdf),
                )
                return pdf
        except Exception:  # noqa: BLE001
            logger.exception("HWP 구조 보존 변환 실패 — 텍스트 폴백을 시도합니다: %s", filename)

    if lower.endswith(".hwpx"):
        text = extract_hwpx_text(content)
    else:
        text = extract_hwp_text(content)

    if not text.strip():
        raise ValueError(
            "HWP를 PDF로 변환하지 못했습니다. "
            "macOS에서는 ./scripts/setup_hancom_hwp_pdf.sh 로 한컴 자동화를 켜거나, "
            "LibreOffice를 설치하거나, 텍스트가 포함된 HWPX/PDF로 올려 주세요."
        )
    return _text_to_pdf(text, title=Path(filename).stem)


def _convert_with_hancom_ui(filename: str, content: bytes) -> bytes:
    """설치된 한컴오피스 한글의 인쇄→PDF로 저장 UI를 조작합니다(요금 없음)."""
    suffix = Path(filename).suffix.lower() or ".hwp"
    with _HANCOM_UI_LOCK:
        with tempfile.TemporaryDirectory(prefix="hancom_hwp_") as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / f"input{suffix}"
            dest = tmp_path / "output.pdf"
            src.write_bytes(content)
            cmd = [
                "osascript",
                str(_HANCOM_SCRIPT),
                str(src.resolve()),
                str(dest.resolve()),
            ]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            if proc.returncode != 0 or not dest.exists():
                detail = (proc.stderr or proc.stdout or "").strip()[:500]
                raise RuntimeError(
                    f"한컴 UI 변환 실패 (code={proc.returncode}): {detail or 'no output'}"
                )
            pdf = dest.read_bytes()
            if not pdf.startswith(b"%PDF") or len(pdf) < 1024:
                raise RuntimeError("한컴 UI가 유효한 PDF를 만들지 못했습니다.")
            return pdf


def peek_hwp_text(filename: str, content: bytes, *, limit: int = 2000) -> str:
    """제목 추천용으로 앞부분만 빠르게 뽑습니다(변환·OCR 없음)."""
    lower = (filename or "").lower()
    try:
        if lower.endswith(".hwpx"):
            text = extract_hwpx_text(content)
        elif lower.endswith(".hwp"):
            text = extract_hwp_text(content)
        else:
            return ""
    except Exception:  # noqa: BLE001
        logger.exception("HWP 미리보기 텍스트 추출 실패: %s", filename)
        return ""
    # 줄바꿈은 유지해 첫 줄 제목 휴리스틱이 동작하게 합니다.
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def extract_hwpx_text(content: bytes) -> str:
    """HWPX(ZIP) 안의 section XML에서 문단 텍스트를 모읍니다."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise ValueError("손상되었거나 HWPX가 아닌 파일입니다.") from exc

    section_names = sorted(
        name
        for name in archive.namelist()
        if re.search(r"(^|/)section\d+\.xml$", name, re.IGNORECASE)
        or name.lower().endswith("/contents/content.hpf")
    )
    # content.hpf는 메타라 본문 우선
    section_names = [n for n in section_names if "section" in n.lower()] or section_names
    paragraphs: list[str] = []
    for name in section_names:
        try:
            xml = archive.read(name)
        except KeyError:
            continue
        paragraphs.extend(_xml_text_lines(xml))
    return "\n".join(paragraphs).strip()


def extract_hwp_text(content: bytes) -> str:
    """구형 HWP(OLE)에서 미리보기·본문 스트림 텍스트를 최대한 모읍니다."""
    import olefile

    if not olefile.isOleFile(io.BytesIO(content)):
        # 일부 파일은 HWPX인데 확장자만 .hwp인 경우가 있습니다.
        if content[:2] == b"PK":
            return extract_hwpx_text(content)
        raise ValueError("OLE 형식의 HWP가 아닙니다.")

    ole = olefile.OleFileIO(io.BytesIO(content))
    chunks: list[str] = []

    # 1) 미리보기 텍스트(UTF-16LE) — 제목·앞머리에 자주 쓰입니다.
    for stream in ("PrvText", "FileHeader"):
        if not ole.exists(stream):
            continue
        raw = ole.openstream(stream).read()
        if stream == "PrvText":
            try:
                text = raw.decode("utf-16-le", errors="ignore").strip("\x00").strip()
            except Exception:  # noqa: BLE001
                text = ""
            if text:
                chunks.append(text)

    # 2) BodyText/Section* — zlib로 압축된 레코드가 흔합니다.
    for entry in ole.listdir():
        path = "/".join(entry)
        if not path.upper().startswith("BODYTEXT"):
            continue
        try:
            raw = ole.openstream(entry).read()
        except Exception:  # noqa: BLE001
            continue
        decoded = _decode_hwp_body_stream(raw)
        if decoded:
            chunks.append(decoded)

    ole.close()
    # 중복·공백 정리
    merged = "\n".join(chunks)
    merged = re.sub(r"[ \t]+\n", "\n", merged)
    merged = re.sub(r"\n{3,}", "\n\n", merged)
    return merged.strip()


def _decode_hwp_body_stream(raw: bytes) -> str:
    """HWP 5 BodyText 섹션에서 읽을 수 있는 문자열만 느슨하게 모읍니다."""
    texts: list[str] = []
    # 통째로 zlib인 경우
    for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
        try:
            inflated = zlib.decompress(raw, wbits)
            texts.append(_bytes_to_koreanish(inflated))
            break
        except Exception:  # noqa: BLE001
            pass

    # 레코드 단위로 앞부분을 훑으며 zlib 블록을 찾습니다.
    i = 0
    while i + 4 < len(raw):
        # HWP record header: tag(10bit) + level(10) + size(12) — 가변이라
        # 휴리스틱으로 zlib 헤더(0x78)만 집어 zlib 시도합니다.
        if raw[i] == 0x78 and raw[i + 1] in (0x01, 0x9C, 0xDA):
            for end in range(i + 8, min(len(raw), i + 200_000), 16):
                try:
                    inflated = zlib.decompress(raw[i:end])
                    piece = _bytes_to_koreanish(inflated)
                    if piece:
                        texts.append(piece)
                    i = end
                    break
                except Exception:  # noqa: BLE001
                    continue
            else:
                i += 1
        else:
            i += 1

    if not texts:
        texts.append(_bytes_to_koreanish(raw))
    return "\n".join(t for t in texts if t).strip()


def _bytes_to_koreanish(data: bytes) -> str:
    """바이너리에서 UTF-16LE/UTF-8 한글·ASCII 줄을 건져냅니다."""
    candidates: list[str] = []
    for enc in ("utf-16-le", "utf-8", "cp949"):
        try:
            text = data.decode(enc, errors="ignore")
        except Exception:  # noqa: BLE001
            continue
        # 제어문자 제거, 짧은 잡음 줄 제거
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
        lines = []
        for line in text.splitlines():
            line = line.strip()
            if len(line) < 2:
                continue
            hangul = len(re.findall(r"[가-힣]", line))
            if hangul >= 2 or (len(line) >= 6 and re.search(r"[A-Za-z0-9가-힣]", line)):
                lines.append(line)
        if lines:
            candidates.append("\n".join(lines))
    if not candidates:
        return ""
    return max(candidates, key=lambda s: len(re.findall(r"[가-힣]", s)))


def _xml_text_lines(xml: bytes) -> list[str]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    lines: list[str] = []
    # hp:t / t 노드가 실제 글자입니다.
    for node in root.iter():
        tag = node.tag.split("}")[-1].lower()
        if tag in {"t", "text"} and (node.text or "").strip():
            lines.append(node.text.strip())
    # 문단 단위로 이어 붙이기 어렵다면 줄바꿈 기준 합치기
    if not lines:
        text = "".join(root.itertext())
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return lines


def _convert_with_libreoffice(soffice: str, filename: str, content: bytes) -> bytes:
    suffix = Path(filename).suffix.lower() or ".hwp"
    with tempfile.TemporaryDirectory(prefix="hwp2pdf_") as tmp:
        tmp_path = Path(tmp)
        src = tmp_path / f"input{suffix}"
        src.write_bytes(content)
        return _libreoffice_file_to_pdf(soffice, src, tmp_path)


def _libreoffice_file_to_pdf(soffice: str, src: Path, output_dir: Path) -> bytes:
    """LibreOffice를 격리 프로필로 실행해 입력 문서를 PDF로 내보냅니다."""
    profile = output_dir / f"lo-profile-{src.stem}"
    profile.mkdir(exist_ok=True)
    profile_uri = profile.resolve().as_uri()
    cmd = [
        soffice,
        f"-env:UserInstallation={profile_uri}",
        "--headless",
        "--nologo",
        "--nodefault",
        "--norestore",
        "--nolockcheck",
        "--convert-to",
        "pdf:writer_pdf_Export",
        "--outdir",
        str(output_dir),
        str(src),
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    pdf_path = output_dir / f"{src.stem}.pdf"
    if not pdf_path.exists():
        matches = list(output_dir.glob("*.pdf"))
        if not matches:
            raise RuntimeError(
                f"LibreOffice 변환 실패 (code={proc.returncode}): "
                f"{(proc.stderr or proc.stdout or '').strip()[:400]}"
            )
        pdf_path = matches[0]
    pdf = pdf_path.read_bytes()
    if not pdf.startswith(b"%PDF") or len(pdf) < 1024:
        raise RuntimeError("LibreOffice가 유효한 PDF를 만들지 못했습니다.")
    return pdf


def _convert_hwp_structured(soffice: str, filename: str, content: bytes) -> bytes:
    """구형 HWP를 pyhwp HTML로 풀어 표·문단·이미지를 보존한 뒤 PDF로 만듭니다."""
    with tempfile.TemporaryDirectory(prefix="hwp5html_") as tmp:
        tmp_path = Path(tmp)
        src = tmp_path / "input.hwp"
        src.write_bytes(content)
        html_dir = tmp_path / "html"
        executable = shutil.which("hwp5html")
        if not executable:
            # venv의 python은 심볼릭 링크일 수 있으므로 resolve()하면 .tools/python으로
            # 빠져 같은 venv의 console script를 찾지 못합니다.
            candidate = Path(sys.executable).parent / "hwp5html"
            executable = str(candidate) if candidate.is_file() else None
        if not executable:
            raise RuntimeError("pyhwp(hwp5html)가 설치되어 있지 않습니다.")

        proc = subprocess.run(
            [executable, "--output", str(html_dir), str(src)],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        html = html_dir / "index.xhtml"
        if proc.returncode != 0 or not html.exists():
            raise RuntimeError(
                f"hwp5html 변환 실패 (code={proc.returncode}): "
                f"{(proc.stderr or proc.stdout or '').strip()[:400]}"
            )
        return _libreoffice_file_to_pdf(soffice, html, tmp_path)


def _convert_hwpx_structured(soffice: str, filename: str, content: bytes) -> bytes:
    """HWPX의 표·이미지·문단 순서를 HTML로 옮긴 뒤 LibreOffice로 PDF화합니다."""
    import markdown
    from airun_hwp.reader.hwpx_reader_ordered import HWPXReaderOrdered

    with tempfile.TemporaryDirectory(prefix="hwpxhtml_") as tmp:
        tmp_path = Path(tmp)
        src = tmp_path / "input.hwpx"
        src.write_bytes(content)
        images_dir = tmp_path / "images"
        images_dir.mkdir()

        document = HWPXReaderOrdered().parse(str(src))
        document.extract_images(str(images_dir))
        markdown_text = document.to_markdown_ordered(
            include_metadata=False,
            images_dir="images",
        )
        body = markdown.markdown(markdown_text, extensions=["tables", "fenced_code"])
        html = tmp_path / "structured.html"
        html.write_text(
            f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>{Path(filename).stem}</title>
<style>
@page {{ size: A4; margin: 18mm; }}
body {{ font-family: "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
        font-size: 10.5pt; line-height: 1.55; color: #111; }}
h1, h2, h3 {{ page-break-after: avoid; }}
table {{ width: 100%; border-collapse: collapse; margin: 8px 0;
         page-break-inside: avoid; font-size: 9.5pt; }}
th, td {{ border: 1px solid #555; padding: 5px 6px; vertical-align: top; }}
th {{ background: #f2f4f7; }}
img {{ max-width: 100%; height: auto; page-break-inside: avoid; }}
p {{ orphans: 2; widows: 2; }}
</style></head><body>{body}</body></html>""",
            encoding="utf-8",
        )
        return _libreoffice_file_to_pdf(soffice, html, tmp_path)


def _text_to_pdf(text: str, *, title: str) -> bytes:
    """검색 가능한 단순 PDF를 만듭니다. 서식은 포기하고 인덱싱 파이프라인에 넘깁니다."""
    import pymupdf

    doc = pymupdf.open()
    fontsize = 11
    margin = 54
    line_height = fontsize * 1.45
    # PyMuPDF 내장 CJK 폰트 — 시스템 폰트를 통째로 넣지 않아 파일이 작습니다.
    fontname = "korea"

    pages_text = text.strip() or title
    lines = pages_text.splitlines() or [title]

    page = doc.new_page(width=595, height=842)  # A4
    y = margin

    def new_page():
        nonlocal page, y
        page = doc.new_page(width=595, height=842)
        y = margin

    for raw_line in lines:
        wrapped = _wrap_line(raw_line, max_chars=48) if raw_line else [""]
        for piece in wrapped:
            if y > 842 - margin - line_height:
                new_page()
            page.insert_text(
                (margin, y),
                piece,
                fontsize=fontsize,
                fontname=fontname,
            )
            y += line_height

    data = doc.tobytes()
    doc.close()
    return data


def _wrap_line(line: str, *, max_chars: int) -> list[str]:
    if len(line) <= max_chars:
        return [line]
    return [line[i : i + max_chars] for i in range(0, len(line), max_chars)]


def _clip(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"
