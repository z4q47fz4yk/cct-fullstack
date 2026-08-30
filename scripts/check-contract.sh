#!/usr/bin/env bash
# 契约一致性校验（合并到 main 前必检）：
#   1) 后端代码导出的 openapi.json 与入库快照一致（漂移即失败）；
#   2) 前端客户端可由快照离线重新生成且类型检查通过。
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