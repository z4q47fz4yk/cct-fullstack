#!/usr/bin/env bash
# 契约/依赖"自愈"共享核心：由 post-merge / post-rewrite 钩子调用。
# 用法：toolchain-sync.sh <old-sha> [<new-sha>]   # 缺省 new = HEAD
#
# 对比 <old>..<new> 两个提交之间的变化，做两件事：
#   1) pnpm-lock.yaml / uv.lock 变化 → 自动安装新增依赖（vp install / uv sync --all-groups）；
#   2) backend/src 或 openapi.json 变化 → 重新导出契约快照；若与入库快照不一致，
#      在工作区落盘并提示（不修改索引/不自动提交，由下一个 commit 收编）。
#
# 设计约束：
# - 只在"成功完成"的 merge/rebase 后被调用（冲突中止时 git 不触发钩子）→ 无冲突标记；
# - 导出确定性（已实测两次导出一致），未变契约时零噪音；
# - venv 缺失等环境问题一律 warn + skip，不报错中断。
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
OLD="${1:?用法: toolchain-sync.sh <old-sha> [<new-sha>]}"
NEW="${2:-$(git rev-parse HEAD)}"

if [ "$OLD" = "$NEW" ]; then
  exit 0
fi

has_change() { # has_change <old> <new> <path...>
  git diff --quiet "$1" "$2" -- "${@:3}" || return 0
  return 1
}

# ---- 1) 依赖锁文件变化 → 自动安装 ----
if has_change "$OLD" "$NEW" pnpm-lock.yaml; then
  echo "[toolchain] 检测到 frontend/pnpm-lock.yaml 变化，运行 vp install ..."
  ( cd "$ROOT/frontend" && vp install ) || echo "[toolchain] warn: vp install 失败（依赖可能未装全，请手动重试）" >&2
fi

if has_change "$OLD" "$NEW" backend/uv.lock; then
  echo "[toolchain] 检测到 backend/uv.lock 变化，运行 uv sync --all-groups ..."
  ( cd "$ROOT/backend" && uv sync --all-groups ) || echo "[toolchain] warn: uv sync 失败（依赖可能未装全，请手动重试）" >&2
fi

# ---- 2) 后端代码 / 契约快照变化 → 重新导出并核对 ----
if has_change "$OLD" "$NEW" backend/src openapi.json; then
  if [ -x "$ROOT/backend/.venv/bin/python" ]; then
    echo "[toolchain] 后端代码或快照变化，重新导出 openapi.json ..."
    bash "$ROOT/scripts/openapi-export.sh"
    if ! git diff --exit-code -- openapi.json >/dev/null; then
      echo "[toolchain] 提示：openapi.json 已与合并/改写后的代码重新同步（工作区变更，未提交，建议随下一个 commit 并入）。"
    else
      echo "[toolchain] openapi.json 与代码一致，无需变更。"
    fi
  else
    echo "[toolchain] warn: backend/.venv 缺失，跳过快照重导出（合并前 check-contract.sh 会兜底校验）" >&2
  fi
fi

exit 0