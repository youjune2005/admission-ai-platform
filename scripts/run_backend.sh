#!/usr/bin/env bash
# Python 3.12(.venv312)로 FastAPI 백엔드를 실행합니다.
set -euo pipefail

BACKEND="$(cd "$(dirname "$0")/../backend" && pwd)"
cd "$BACKEND"

if [[ ! -x .venv312/bin/python ]]; then
  echo ".venv312 가 없습니다. 먼저 scripts/setup_venv312.sh 를 실행하세요."
  exit 1
fi

exec .venv312/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 "$@"
