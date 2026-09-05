#!/usr/bin/env bash
# pre-commit 契约配套步骤（由 frontend/.vite-hooks/pre-commit 在 `vp staged` 之后调用）。
#
# 为什么不在 pre-commit-format.sh（lint-staged 任务）里做：lint-staged 用 stash 暂存/恢复索引，
# 任务内的 `git add` 会被其恢复流程丢弃；本脚本基于**最终暂存集**（vp staged 格式化/复暂存之后）
# 判断，直接在真实索引上导出并 add，确保快照随本次提交入库。
#
# 触发：`git diff --cached` 含 backend/src/**（任何后端源码都可能影响 OpenAPI）。
# 导出确定性（未变契约则零噪音）；venv 缺失 → warn + skip，由合并前 check-contract.sh 兜底。
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"

if ! git diff --cached --name-only | grep -q '^backend/src/'; then
  exit 0
fi

if [ ! -x "$ROOT/backend/.venv/bin/python" ]; then
  echo "[pre-commit] warn: backend/.venv 缺失，跳过 openapi.json 自动导出（请运行 scripts/worktree-bootstrap.sh）" >&2
  exit 0
fi

bash "$ROOT/scripts/openapi-export.sh"
git add "$ROOT/openapi.json"
if ! git diff --cached --quiet -- openapi.json; then
  echo "[pre-commit] 已自动重新导出 openapi.json 并加入本次提交（契约配套）。"
fi
exit 0