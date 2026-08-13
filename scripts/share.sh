#!/usr/bin/env bash
# 공개 URL 공유용 Cloudflare 터널 (+ 단축 링크 출력)
# 프로젝트 루트에서 실행:  ./scripts/share.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${SHARE_PORT:-5173}"
TARGET="http://127.0.0.1:${PORT}"
cd "$ROOT"
LOG_DIR="$ROOT/.share-logs"
mkdir -p "$LOG_DIR"
CF_LOG="$LOG_DIR/cloudflared-share.log"

echo "==> SSU 입시행정 AI — 공개 URL 공유"
echo "    프로젝트: $ROOT"
echo "    대상:     $TARGET"
echo ""

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "❌ cloudflared 가 설치되어 있지 않습니다."
  echo ""
  echo "터미널에서 한 번만 설치하세요:"
  echo "  brew install cloudflared"
  echo ""
  echo "brew 권한이 안 되면:"
  echo "  sudo chown -R \"\$(whoami)\" /usr/local/Cellar /usr/local/Homebrew 2>/dev/null || true"
  echo "  brew install cloudflared"
  echo ""
  echo "또는 Cloudflare 설치 안내:"
  echo "  https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/"
  exit 1
fi

if ! curl -sf -o /dev/null --max-time 2 "${TARGET}/"; then
  echo "❌ 프론트가 ${TARGET} 에서 응답하지 않습니다."
  echo "   다른 터미널에서 먼저:"
  echo "   cd \"$ROOT/frontend\" && npm run dev:share"
  exit 1
fi

if ! curl -sf -o /dev/null --max-time 2 "http://127.0.0.1:8000/api/health"; then
  echo "❌ 백엔드가 http://127.0.0.1:8000 에서 응답하지 않습니다."
  echo "   다른 터미널에서 먼저:"
  echo "   cd \"$ROOT/backend\" && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000"
  exit 1
fi

cleanup() {
  if [[ -n "${CF_PID:-}" ]] && kill -0 "$CF_PID" 2>/dev/null; then
    kill "$CF_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

echo "==> Cloudflare Quick Tunnel 시작"
: >"$CF_LOG"
cloudflared tunnel --url "${TARGET}" >"$CF_LOG" 2>&1 &
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
  echo "공개 URL을 아직 못 찾았습니다. 로그: $CF_LOG"
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
echo "    종료: Ctrl+C"
echo ""

wait "$CF_PID"
