# 입시행정 통합 지원 시스템 (Admission AI Platform)

생성형 AI 기반으로 대학 입시행정 업무를 지원하는 통합 플랫폼입니다. 내부 입시행정 담당자를 위한
AI 상담 챗봇, 데이터 분석, 업무 자동화(공지문 초안 생성), 지원 서류 검토 기능을 제공합니다.

## 구성

- `backend/` — FastAPI 기반 API 서버 (Python)
- `frontend/` — React + Vite + TypeScript + Tailwind CSS 기반 웹 대시보드
- `data/` — 입시 관련 참고 데이터를 넣는 폴더 (모집요강, 과거 통계 등)

## 주요 기능

| 기능 | 설명 |
| --- | --- |
| AI 상담 (`/chat`) | 입시행정 관련 질의응답 챗봇 (세션별 대화 이력 저장) |
| 데이터 분석 (`/analytics`) | CSV/Excel 업로드 → 통계 요약 + AI 인사이트 생성 |
| 업무 자동화 (`/workflow`) | 업무 태스크 관리 + AI 공지문 초안 자동 생성 |
| 서류 검토 (`/documents`) | PDF/텍스트 서류 업로드 → AI 핵심 요약 및 확인 필요 항목 추출 |

## LLM 연동

`backend/app/services/llm_service.py`에서 OpenAI, Anthropic을 공용 인터페이스로 지원합니다.
API 키가 설정되어 있지 않으면 자동으로 **mock 모드**로 동작하므로, 키 없이도 전체 화면과
흐름을 바로 확인할 수 있습니다.

## 실행 방법

### 백엔드

스캔 PDF OCR은 **로컬 OCR → CLOVA(선택) → GPT-4o Vision** 순으로 동작합니다.
로컬 OCR은 기본적으로 RapidOCR(PP-OCRv4 한국어 모델 + ONNX Runtime)을 쓰며,
모델은 첫 실행 때 자동으로 내려받습니다. 인텔 맥 기준 페이지당 약 16초로,
같은 모델을 PaddleOCR로 돌릴 때(약 80초)보다 4~5배 빠릅니다.

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 필요 시 OPENAI_API_KEY / ANTHROPIC_API_KEY 입력
uvicorn app.main:app --reload
```

CLOVA OCR을 쓰려면 `backend/.env`에 네이버 클라우드 General OCR의 Invoke URL / Secret을 넣으세요.

```bash
CLOVA_OCR_INVOKE_URL=https://....apigw.ntruss.com/.../general
CLOVA_OCR_SECRET=...
CLOVA_OCR_ENABLE_TABLE=true
```

미설정이어도 동작하며, 그때는 로컬 OCR 다음이 바로 GPT Vision입니다.

HWP/HWPX 업로드는 서버에서 PDF로 바꾼 뒤 위와 같은 파이프라인으로 인덱싱합니다.

**변환 우선순위 (추가 요금 없음)**

1. **한컴오피스 한글 UI 자동화** (macOS, 선택) — 설치된 한글 앱의 인쇄→PDF 저장을
   조작합니다. 원본에 가장 가깝습니다. 한 번만 접근성(Accessibility) 권한을 주면 됩니다.
   ```bash
   ./scripts/setup_hancom_hwp_pdf.sh [/path/to/sample.hwp]
   # backend/.env 에 HWP_USE_HANCOM_UI=true 가 들어갑니다. 서버를 재시작하세요.
   ```
   GUI 세션이 있는 Mac에서만 동작합니다(헤드리스 서버·SSH 전용은 불가).
2. **LibreOffice** (`brew install --cask libreoffice`) 직접 변환.
3. 구조 보존 폴백 — HWP는 pyhwp HTML, HWPX는 표·이미지 HTML → 다시 PDF.
4. 본문 텍스트만 뽑은 검색용 PDF.

한컴 경로가 실패해도(권한·UI 변경 등) 2→3→4로 자동 폴백합니다.

PaddleOCR로 되돌리려면 `.env`에 `OCR_LOCAL_ENGINE=paddle`을 넣고 Python 3.12 환경을 씁니다
(Paddle 휠이 3.10–3.12만 지원).

```bash
./scripts/setup_venv312.sh   # 최초 1회
./scripts/run_backend.sh
```

기본적으로 `http://localhost:8000` 에서 실행되며, API 문서는 `http://localhost:8000/docs` 에서 확인할 수 있습니다.

### 프론트엔드

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

기본적으로 `http://localhost:5173` 에서 실행됩니다.

## 공개 URL로 단기 공유 (도메인 없이)

API 키는 **항상 `backend/.env`에만** 둡니다. 프론트엔드에는 키가 없습니다.
공유할 때는 Vite가 `/api`를 백엔드로 프록시하므로, 브라우저에는 키·백엔드 주소가 노출되지 않습니다.

### 1) 백엔드

```bash
cd backend
source .venv/bin/activate
# 선택: 단기 데모용 CORS 전체 허용
# echo 'CORS_ALLOW_ALL=true' >> .env
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 2) 프론트 (공유 모드)

```bash
cd frontend
npm run dev:share
```

`VITE_API_BASE_URL`을 비워 `/api` → `localhost:8000` 프록시를 사용합니다.

### 3) Cloudflare 무료 터널 URL 발급

```bash
./scripts/share.sh
```

터미널에 나오는 `https://xxxx.trycloudflare.com` 주소를 공유하면 됩니다.  
(최초 1회 `brew install cloudflared` 필요할 수 있습니다.)

### 보안 요약

| 항목 | 이 프로젝트 |
| --- | --- |
| API 키 위치 | `backend/.env` only (브라우저 F12에 안 보임) |
| 공개 URL | Cloudflare Quick Tunnel (HTTPS) |
| 남용 완화 | IP당 분당 `RATE_LIMIT_PER_MINUTE`(기본 60) |

장기 배포는 Vercel(프론트) + Railway/Render(백엔드) 조합을 권장합니다. 서버리스만으로 FastAPI+SQLite RAG 전체를 넣기는 어렵습니다.

## 데이터 반영 방법 (RAG)

입시 관련 문서(모집요강 PDF, 안내문, FAQ 등)를 `data/` 폴더 하위에 넣고 서류 검토
화면에서 **"data/ 폴더 동기화"** 버튼을 누르면:

1. 폴더 내 새 파일(PDF/TXT/MD)을 자동으로 찾아 텍스트를 추출하고
2. AI 요약을 생성하며
3. 내용을 청크로 분할해 임베딩 후 저장합니다.

이후 **AI 상담 챗봇**은 질문과 관련된 문서 내용을 자동으로 검색해 답변에 반영합니다
(예: "2027학년도 수시모집 원서접수 기간이 언제야?" → 실제 업로드된 모집요강 내용을 인용해 답변).

물론 각 화면(데이터 분석/서류 검토)에서 파일을 직접 업로드해 즉시 분석·요약해보는 것도 가능합니다.
CSV/Excel 통계 데이터는 임베딩 대상이 아니라 데이터 분석 화면에서 통계/인사이트로 활용됩니다.

임베딩에는 OpenAI API 키가 필요합니다(`OPENAI_API_KEY`). 키가 없으면 RAG 검색은 비활성화되고
일반 지식 기반으로만 답변합니다.

민감한 개인정보(주민등록번호, 연락처 등)는 가급적 비식별화 후 전달해주세요.

## 배포 시 참고

현재는 OpenAI/Anthropic 등 외부 클라우드 LLM API 사용을 전제로 구성되어 있습니다.
추후 온프레미스/로컬 LLM으로 전환이 필요하면 `llm_service.py`에 로컬 모델(Provider) 어댑터를
추가하는 방식으로 확장 가능합니다.
