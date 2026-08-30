#!/usr/bin/env bash
# 从入库的根 openapi.json 离线重新生成前端客户端（无需后端运行）。
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT/frontend"
exec vpr generate-api