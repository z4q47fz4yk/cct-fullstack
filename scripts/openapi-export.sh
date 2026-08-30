#!/usr/bin/env bash
# 从后端代码导出 OpenAPI 契约到仓库根 openapi.json（入库快照，供客户端离线生成）。
# 离线安全：仅导入 app 对象，不触发 lifespan（不连接数据库）。
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT/backend"

if [ ! -x .venv/bin/python ]; then
  echo "错误：backend/.venv 未就绪，请先运行 scripts/worktree-bootstrap.sh（或 uv sync --all-groups）" >&2
  exit 1
fi

.venv/bin/python - "$ROOT" <<'PY'
import json
import sys

from src.app import app

root = sys.argv[1]
out = f"{root}/openapi.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump(app.openapi(), f, ensure_ascii=False, indent=2)
    f.write("\n")
print(f"已导出 OpenAPI 契约: {out}")
PY