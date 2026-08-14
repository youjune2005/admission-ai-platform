#!/usr/bin/env bash
# Python 3.12 venv + PaddleOCR 환경을 구성합니다.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
cd "$BACKEND"

export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$BACKEND/.tools/python}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$BACKEND/.tools/uv-cache}"

if [[ ! -x "$BACKEND/.tools/uv" ]]; then
  echo "uv 바이너리가 없습니다. GitHub에서 받아 .tools/uv 에 두세요."
  echo "  https://github.com/astral-sh/uv/releases"
  exit 1
fi

"$BACKEND/.tools/uv" python install 3.12
"$BACKEND/.tools/uv" venv --python 3.12 .venv312
.venv312/bin/python -m ensurepip --upgrade
.venv312/bin/python -m pip install -U pip setuptools wheel
.venv312/bin/python -m pip install "paddlepaddle==2.6.2"
.venv312/bin/python -m pip install -r requirements.txt

echo
echo "완료: $BACKEND/.venv312"
echo "백엔드 실행:"
echo "  cd backend && source .venv312/bin/activate && uvicorn app.main:app --reload --port 8000"
echo
echo "CLOVA OCR을 쓰려면 backend/.env 에 다음을 넣으세요:"
echo "  CLOVA_OCR_INVOKE_URL=https://....apigw.ntruss.com/.../general"
echo "  CLOVA_OCR_SECRET=..."
echo "  CLOVA_OCR_ENABLE_TABLE=true"
