#!/usr/bin/env bash
# post-merge 钩子入口（git merge / git pull 成功后触发，冲突中止不触发）。
# 解析合并前 HEAD 并交给 scripts/toolchain-sync.sh 处理依赖安装与契约快照同步。
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"

# 合并前的 HEAD（reflog）。刚合并完成时 HEAD@{1} 即为旧 tip；取不到则跳过。
if OLD="$(git rev-parse -q --verify HEAD@{1} 2>/dev/null)"; then
  exec bash "$ROOT/scripts/toolchain-sync.sh" "$OLD"
fi
exit 0