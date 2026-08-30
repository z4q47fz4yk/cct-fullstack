#!/usr/bin/env bash
# 启动前端 dev server：端口取根 .env 的 FRONTEND_PORT（缺省 5173），strictPort 冲突即报错。
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
ENV_FILE="$ROOT/.env"
[ -f "$ENV_FILE" ] && set -a && . "$ENV_FILE" && set +a

cd "$ROOT/frontend"
exec vp dev