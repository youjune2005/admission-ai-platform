# shellcheck shell=bash
# zip1.io 로 단축 (trycloudflare 허용, 중간 광고 페이지 없음)
# 사용: SHORT="$(shorten_url "$LONG")"
shorten_url() {
  local long="${1:-}"
  local raw short
  [[ -z "$long" ]] && { printf '%s' ""; return 0; }

  raw="$(
    curl -4 -sS --max-time 15 \
      -A "Mozilla/5.0" \
      -X POST "https://zip1.io/api/create" \
      -H "Content-Type: application/json" \
      -d "{\"url\":\"${long}\"}" 2>/dev/null || true
  )"

  short="$(
    SHORTEN_RAW="$raw" python3 - <<'PY' 2>/dev/null || true
import json, os
raw = os.environ.get("SHORTEN_RAW", "").strip()
if not raw:
    raise SystemExit(0)
try:
    data = json.loads(raw)
except Exception:
    raise SystemExit(0)
url = (data.get("short_url") or data.get("shortUrl") or "").strip()
if url.startswith("http://"):
    url = "https://" + url[len("http://"):]
if url.startswith("https://"):
    print(url, end="")
PY
  )"

  printf '%s' "$short"
}
