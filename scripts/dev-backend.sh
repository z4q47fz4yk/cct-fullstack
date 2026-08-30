#!/usr/bin/env bash
# 启动后端 dev server：端口取根 .env 的 BACKEND_PORT（缺省 8000）。
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
ENV_FILE="$ROOT/.env"
[ -f "$ENV_FILE" ] && set -a && . "$ENV_FILE" && set +a

cd "$ROOT/backend"
if [ ! -x .venv/bin/fastapi ]; then
  echo "错误：backend/.venv 未就绪，请先运行 scripts/worktree-bootstrap.sh（或 uv sync --all-groups）" >&2
  exit 1
fi
source .venv/bin/activate
exec fastapi dev src/app.py --port "${BACKEND_PORT:-8000}"