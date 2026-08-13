#!/usr/bin/env bash
# 백엔드·프론트·Cloudflare 터널을 한 번에 띄우고, 공개 URL을 브라우저로 엽니다.
# 사용: 아래 한 줄을 터미널에 붙여넣기
#   cd /Users/youjune/CursorProjects/admission-ai-platform && ./scripts/open-share.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PORT=5173
LOG_DIR="$ROOT/.share-logs"
mkdir -p "$LOG_DIR"
BE_LOG="$LOG_DIR/backend.log"
FE_LOG="$LOG_DIR/frontend.log"
CF_LOG="$LOG_DIR/cloudflared.log"

cleanup() {
  # Ctrl+C 시 터널만 종료 (로컬 서버는 유지)
  if [[ -n "${CF_PID:-}" ]] && kill -0 "$CF_PID" 2>/dev/null; then
    kill "$CF_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

echo "==> 프로젝트: $ROOT"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared 가 없습니다. 먼저: brew install cloudflared"
  exit 1
fi

# 백엔드
if ! curl -sf -o /dev/null --max-time 2 "http://127.0.0.1:8000/api/health"; then
  echo "==> 백엔드 시작…"
  nohup "$ROOT/backend/.venv/bin/uvicorn" app.main:app \
    --host 127.0.0.1 --port 8000 \
    >"$BE_LOG" 2>&1 &
  for i in {1..30}; do
    curl -sf -o /dev/null --max-time 1 "http://127.0.0.1:8000/api/health" && break
    sleep 0.5
  done
  if ! curl -sf -o /dev/null --max-time 2 "http://127.0.0.1:8000/api/health"; then
    echo "백엔드 기동 실패. 로그: $BE_LOG"
    tail -n 40 "$BE_LOG" || true
    exit 1
  fi
else
  echo "==> 백엔드 이미 실행 중"
fi

# 프론트 (공유 모드: API 프록시)
NEED_FE_RESTART=1
if curl -sf -o /dev/null --max-time 2 "http://127.0.0.1:${PORT}/"; then
  echo "==> 기존 프론트를 공유 모드로 재시작합니다…"
fi

if [[ "$NEED_FE_RESTART" == "1" ]]; then
  echo "==> 프론트 공유 모드 시작…"
  if command -v lsof >/dev/null 2>&1; then
    PIDS="$(lsof -tiTCP:"${PORT}" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "$PIDS" ]]; then
      # shellcheck disable=SC2086
      kill $PIDS 2>/dev/null || true
      sleep 1
    fi
  fi
  (
    cd "$ROOT/frontend"
    export VITE_API_BASE_URL=
    nohup npm run dev:share >"$FE_LOG" 2>&1 &
  )
  for i in {1..40}; do
    curl -sf -o /dev/null --max-time 1 "http://127.0.0.1:${PORT}/" && break
    sleep 0.5
  done
  if ! curl -sf -o /dev/null --max-time 2 "http://127.0.0.1:${PORT}/"; then
    echo "프론트 기동 실패. 로그: $FE_LOG"
    tail -n 40 "$FE_LOG" || true
    exit 1
  fi
fi

echo "==> Cloudflare 터널 연결 중… (URL이 나오면 브라우저를 엽니다)"
: >"$CF_LOG"
cloudflared tunnel --url "http://127.0.0.1:${PORT}" >"$CF_LOG" 2>&1 &
CF_PID=$!

PUBLIC_URL=""
for i in {1..60}; do
  PUBLIC_URL="$(grep -Eo 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' "$CF_LOG" | head -n 1 || true)"
  if [[ -n "$PUBLIC_URL" ]]; then
    break
  fi
  if ! kill -0 "$CF_PID" 2>/dev/null; then
    echo "cloudflared 가 종료되었습니다. 로그:"
    cat "$CF_LOG"
    exit 1
  fi
  sleep 0.5
done

if [[ -z "$PUBLIC_URL" ]]; then
  echo "공개 URL을 아직 못 찾았습니다. 로그를 확인하세요: $CF_LOG"
  tail -n 50 "$CF_LOG" || true
  wait "$CF_PID"
  exit 1
fi

# shellcheck source=scripts/_shorten.sh
source "$ROOT/scripts/_shorten.sh"
SHORT_URL="$(shorten_url "$PUBLIC_URL")"

echo ""
echo "✅ 공유 주소: $PUBLIC_URL"
if [[ -n "$SHORT_URL" ]]; then
  echo "✅ 단축 링크: $SHORT_URL"
  if command -v pbcopy >/dev/null 2>&1; then
    printf '%s' "$SHORT_URL" | pbcopy
    echo "   (단축 링크를 클립보드에 복사했습니다)"
  fi
else
  echo "⚠️  단축 실패 — 위 공유 주소를 사용하세요."
  if command -v pbcopy >/dev/null 2>&1; then
    printf '%s' "$PUBLIC_URL" | pbcopy
    echo "   (원본 주소를 클립보드에 복사했습니다)"
  fi
fi
echo "   (이 터미널을 닫거나 Ctrl+C 하면 터널이 끊깁니다)"
echo ""

if command -v open >/dev/null 2>&1; then
  open "$PUBLIC_URL"
fi

# 터널 유지
wait "$CF_PID"
