#!/usr/bin/env bash
# vite-plus pre-commit 钩子（由根 vite.config.ts 的 staged 配置调用）的分发脚本：
# - frontend/*（.ts/.vue/.js/.md 等）→ oxlint/oxfmt：cd frontend && vp check --fix <files>
# - backend/*.py → ruff：ruff check --fix + ruff format
# - 其余文件跳过（根目录文档等）
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
FE=()
PY=()
VUE=()
for f in "$@"; do
  case "$f" in
    # 仅代码文件交给 oxfmt；文档（.md 等）保持作者格式，避免钩子改写
    frontend/*.ts | frontend/*.tsx | frontend/*.vue | frontend/*.js | frontend/*.jsx | frontend/*.mts | frontend/*.cts | frontend/*.json | frontend/*.jsonc) FE+=("${f#frontend/}") ;;
    backend/*.py) PY+=("${f#backend/}") ;;
  esac
  case "$f" in
    frontend/*.vue) VUE+=("$f") ;;
  esac
done

if [ "${#FE[@]}" -gt 0 ]; then
  ( cd "$ROOT/frontend" && vp check --fix "${FE[@]}" )
fi
if [ "${#VUE[@]}" -gt 0 ]; then
  # 暂存的 Vue 模板做废弃类名拦截（清单见 scripts/check-deprecated-classes.sh）
  bash "$ROOT/scripts/check-deprecated-classes.sh" "${VUE[@]}"
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