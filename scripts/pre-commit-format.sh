#!/usr/bin/env bash
# vite-plus pre-commit 钩子（由根 vite.config.ts 的 staged 配置调用）的分发脚本：
# - frontend/*（.ts/.vue/.js/.md 等）→ oxlint/oxfmt：cd frontend && vp check --fix <files>
# - backend/*.py → ruff：ruff check --fix + ruff format
# - 其余文件跳过（根目录文档等）
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
FE=()
PY=()
for f in "$@"; do
  case "$f" in
    frontend/*) FE+=("${f#frontend/}") ;;
    backend/*.py) PY+=("${f#backend/}") ;;
  esac
done

if [ "${#FE[@]}" -gt 0 ]; then
  ( cd "$ROOT/frontend" && vp check --fix "${FE[@]}" )
fi
if [ "${#PY[@]}" -gt 0 ]; then
  (
    cd "$ROOT/backend"
    # ruff/ty 为全局工具（见 backend/AGENTS.md），venv 内没有；.venv/bin/ruff 仅作兜底
    if command -v ruff >/dev/null 2>&1; then
      ruff check --fix "${PY[@]}"
      ruff format "${PY[@]}"
    elif [ -x .venv/bin/ruff ]; then
      .venv/bin/ruff check --fix "${PY[@]}"
      .venv/bin/ruff format "${PY[@]}"
    else
      echo "warn: 找不到 ruff，跳过 Python 格式化" >&2
    fi
  )
fi

exit 0