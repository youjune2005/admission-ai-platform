#!/usr/bin/env bash
# 한컴오피스 한글(macOS) UI 자동화로 HWP→PDF 변환 환경을 점검합니다.
# 요금 없음. 접근성 권한만 한 번 허용하면 됩니다.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$ROOT/scripts/hancom_hwp_to_pdf.applescript"
BACKEND="$ROOT/backend"

echo "== 한컴 HWP→PDF 자동화 점검 =="

if [[ ! -d "/Applications/Hancom Office HWP.app" ]]; then
  echo "❌ /Applications/Hancom Office HWP.app 이 없습니다."
  echo "   App Store/한컴에서 한글(macOS)을 설치한 뒤 다시 실행하세요."
  exit 1
fi
echo "✅ 한컴오피스 한글 앱 발견"

if [[ ! -f "$SCRIPT" ]]; then
  echo "❌ $SCRIPT 가 없습니다."
  exit 1
fi
echo "✅ AppleScript 변환기 발견"

echo
echo "macOS 접근성(Accessibility)에서 아래 앱에 체크가 필요합니다:"
echo "  - Terminal (또는 iTerm)"
echo "  - Cursor (Cursor에서 서버를 띄우는 경우)"
echo "  - Python / uvicorn 을 직접 실행하는 터미널 앱"
echo
open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility" 2>/dev/null || \
  open "/System/Library/PreferencePanes/Security.prefPane" 2>/dev/null || true

echo "권한을 켠 뒤 Enter 를 누르세요…"
read -r _

# 샘플이 없으면 최소 HWPX를 임시로 만들어 볼 수 없으므로, 사용자가 준 경로 또는 mdfind
SAMPLE="${1:-}"
if [[ -z "$SAMPLE" ]]; then
  SAMPLE="$(mdfind 'kMDItemFSName == "*.hwp"c' 2>/dev/null | grep -v '/Applications/' | head -1 || true)"
fi

if [[ -z "$SAMPLE" || ! -f "$SAMPLE" ]]; then
  echo "⚠️  테스트용 .hwp 파일을 찾지 못했습니다."
  echo "   사용법: $0 /path/to/sample.hwp"
  echo
  echo "backend/.env 에 다음을 넣으면 업로드 시 한컴 자동화를 시도합니다:"
  echo "  HWP_USE_HANCOM_UI=true"
  exit 0
fi

OUT="$(mktemp -t hancom-hwp-test).pdf"
echo "테스트 변환: $SAMPLE"
echo "출력: $OUT"

if osascript "$SCRIPT" "$SAMPLE" "$OUT"; then
  BYTES="$(wc -c < "$OUT" | tr -d ' ')"
  echo "✅ 변환 성공 (${BYTES} bytes)"
  echo "   open \"$OUT\""
else
  CODE=$?
  echo "❌ 변환 실패 (exit=$CODE)"
  echo "   접근성 권한이 꺼져 있거나, 인쇄 시트 UI가 버전과 다를 수 있습니다."
  echo "   실패해도 업로드는 LibreOffice/구조보존/텍스트 PDF 폴백으로 계속됩니다."
  exit "$CODE"
fi

if [[ -f "$BACKEND/.env" ]] && ! grep -q '^HWP_USE_HANCOM_UI=' "$BACKEND/.env"; then
  echo >> "$BACKEND/.env"
  echo "HWP_USE_HANCOM_UI=true" >> "$BACKEND/.env"
  echo "✅ backend/.env 에 HWP_USE_HANCOM_UI=true 를 추가했습니다."
elif [[ -f "$BACKEND/.env" ]]; then
  echo "ℹ️  backend/.env 의 HWP_USE_HANCOM_UI 설정을 확인하세요."
else
  echo "backend/.env 예시:"
  echo "  HWP_USE_HANCOM_UI=true"
fi
