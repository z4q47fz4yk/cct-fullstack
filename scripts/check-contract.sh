#!/usr/bin/env bash
# 契约一致性校验：
#   1) 后端代码导出的 openapi.json 与入库快照一致（漂移即失败）；
#   2) 前端客户端可由快照离线重新生成且类型检查通过。
#
# 适用时机（commit 时的快照已由 pre-commit 钩子在改动 backend/src 时自动维护，本脚本不为此服务）：
# - rebase / merge 冲突解决之后（快照可能被 3-way 合并或手工解析改写）；
# - 合并/推送 main 前的最终闸门；
# - 任何时刻对脏树抽查（如拉入他人提交后）。
# 后两类场景 git 侧自动触发路径见 scripts/toolchain-sync.sh（post-merge / post-rewrite 钩子）。
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"

bash "$ROOT/scripts/openapi-export.sh"

cd "$ROOT"
if ! git diff --exit-code -- openapi.json; then
  echo ">>> 契约漂移：后端代码与入库 openapi.json 不一致。" >&2
  echo ">>> 若为有意变更：执行 scripts/openapi-export.sh，并将 openapi.json 与配套前端代码放入同一提交。" >&2
  exit 1
fi

bash "$ROOT/scripts/gen-client.sh"
( cd "$ROOT/frontend" && vpr type-check )

echo "契约校验通过：openapi.json 与后端代码一致，前端客户端可离线重新生成。"