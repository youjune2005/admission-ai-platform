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

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 필요 시 OPENAI_API_KEY / ANTHROPIC_API_KEY 입력
uvicorn app.main:app --reload
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
