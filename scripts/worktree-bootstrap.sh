#!/usr/bin/env bash
# 新建 worktree 后的一键引导：分配端口 → 同步依赖 → 离线生成客户端 → 类型检查。
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
SCRIPTS="$ROOT/scripts"

bash "$SCRIPTS/worktree-env.sh"

echo "==> 后端依赖 (uv sync --all-groups)"
( cd "$ROOT/backend" && uv sync --all-groups )

echo "==> 前端依赖 (vp install)"
( cd "$ROOT/frontend" && vp install )

echo "==> 从入库 openapi.json 离线生成客户端 (vpr generate-api)"
( cd "$ROOT/frontend" && vpr generate-api )

echo "==> 类型检查 (vpr type-check)"
( cd "$ROOT/frontend" && vpr type-check )

echo "bootstrap 完成。启动：scripts/dev-backend.sh / scripts/dev-frontend.sh / scripts/dev-docs.sh"