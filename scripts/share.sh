#!/usr/bin/env bash
# 공개 URL 공유용 Cloudflare 터널
# 프로젝트 루트에서 실행:  ./scripts/share.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${SHARE_PORT:-5173}"
TARGET="http://127.0.0.1:${PORT}"
cd "$ROOT"

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

echo "==> Cloudflare Quick Tunnel 시작"
echo "    https://xxxx.trycloudflare.com 주소가 나오면 그걸 공유하세요."
echo "    종료: Ctrl+C"
echo ""

exec cloudflared tunnel --url "${TARGET}"
