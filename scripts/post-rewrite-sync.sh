#!/usr/bin/env bash
# post-rewrite 钩子入口（成功的 rebase / commit --amend / cherry-pick 后触发）。
# 求改写前的分支 tip 并交给 scripts/toolchain-sync.sh 处理依赖安装与契约快照同步。
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
BRANCH="$(git symbolic-ref --short -q HEAD 2>/dev/null || true)"

# 主路径：当前分支 reflog 前一条 = 改写前 tip（rebase / amend 均适用）
OLD=""
if [ -n "$BRANCH" ]; then
  OLD="$(git rev-parse -q --verify "refs/heads/$BRANCH@{1}" 2>/dev/null || true)"
fi

# 兜底：从 post-rewrite stdin 的 <old> <new> 行里找"new == 当前 HEAD"的 old
if [ -z "$OLD" ]; then
  HEAD_SHA="$(git rev-parse HEAD)"
  while read -r old new _extra; do
    [ -n "$new" ] || continue
    if [ "$new" = "$HEAD_SHA" ]; then
      OLD="$old"
      break
    fi
  done
fi

if [ -n "$OLD" ]; then
  exec bash "$ROOT/scripts/toolchain-sync.sh" "$OLD"
fi
exit 0