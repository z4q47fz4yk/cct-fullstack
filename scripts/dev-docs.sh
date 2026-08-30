#!/usr/bin/env bash
# 启动文档站 dev server（vitepress）：端口取根 .env 的 DOCS_PORT（缺省 5174）。
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
ENV_FILE="$ROOT/.env"
[ -f "$ENV_FILE" ] && set -a && . "$ENV_FILE" && set +a

cd "$ROOT/frontend"
exec pnpm docs:dev