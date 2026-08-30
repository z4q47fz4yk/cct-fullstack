#!/usr/bin/env bash
# 为当前 worktree 分配端口三元组（后端/前端/docs）并写入仓库根 .env。
#
# - 前后端/docs 从同一份根 .env 读取端口 ⇒ 同一 worktree 内天然一一对应，
#   解决"前端不知道哪个端口对应自己的后端"；
# - 幂等：重复执行会基于其他 worktree 当前占用情况重新分配（自己旧的端口不计入占用）；
# - 已有 .env 的非端口键（如 DATABASE_URL）会被保留。
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
ENV_FILE="$ROOT/.env"

# 从 .env 中读取指定键的值（不做 source，避免执行任意内容）
read_env() {
  local file="$1" key="$2" line val
  [ -f "$file" ] || return 1
  while IFS= read -r line; do
    case "$line" in
      "$key="*)
        val="${line#"$key="}"
        printf '%s' "$val"
        return 0
        ;;
    esac
  done <"$file"
  return 1
}

# 收集其他 worktree 已占用的端口（跳过自身，保证重跑时端口稳定）。
# 用空白分隔的字符串集合代替关联数组，兼容 macOS 默认 bash 3.2。
used=""
mark_used() { used="$used $1"; }
is_used() {
  local p="$1"
  case " $used " in
    *" $p "*) return 0 ;;
    *) return 1 ;;
  esac
}

while read -r wt; do
  [ -n "$wt" ] || continue
  [ "$wt" = "$ROOT" ] && continue
  for key in BACKEND_PORT FRONTEND_PORT DOCS_PORT; do
    if val="$(read_env "$wt/.env" "$key")" && [ -n "$val" ]; then
      mark_used "$val"
    fi
  done
done < <(git worktree list --porcelain | awk '/^worktree /{print $2}')

# 主 worktree = git worktree list 的第一项
main_wt="$(git worktree list --porcelain | awk '/^worktree /{print $2; exit}')"

# 当前 worktree 尚无 .env 时：复制主 worktree 的 .env 作为基底
# （保留 DATABASE_URL 等既有键；端口随后会被覆盖）
if [ ! -f "$ENV_FILE" ] && [ -n "$main_wt" ] && [ -f "$main_wt/.env" ]; then
  cp "$main_wt/.env" "$ENV_FILE"
  echo "已复制主 worktree 的 .env 作为基底: $main_wt/.env"
fi

# 在三个独立区间各取最小空闲端口（每选一个立即标记占用，避免区间互相重叠）
pick_port() {
  local p="$1"
  while is_used "$p"; do p=$((p + 1)); done
  mark_used "$p"
  printf '%d' "$p"
}
BACKEND_PORT="$(pick_port 8000)"
FRONTEND_PORT="$(pick_port 5173)"
DOCS_PORT="$(pick_port 5174)"

# 写回：剔除被覆写的键，追加新值（保留其余键与注释），最后原子替换
TMP="$(mktemp)"
if [ -f "$ENV_FILE" ]; then
  # 保留既有键与用户注释；剔除端口相关键、脚本自带的注释与空行
  grep -v -E '^[[:space:]]*$|^\s*(BACKEND_PORT|FRONTEND_PORT|DOCS_PORT|VITE_API_BASE|CORS_ALLOW_ALL)=|^# ---- 端口三元组|^# 开发期放开 CORS' "$ENV_FILE" >"$TMP" || true
else
  : >"$TMP"
fi
cat >>"$TMP" <<EOF
# ---- 端口三元组（由 scripts/worktree-env.sh 维护；前后端共用，保证一一对应）----
BACKEND_PORT=$BACKEND_PORT
FRONTEND_PORT=$FRONTEND_PORT
DOCS_PORT=$DOCS_PORT
VITE_API_BASE=http://localhost:$BACKEND_PORT
# 开发期放开 CORS 允许任意来源（allow_origins=[*]，此时 allow_credentials=False）
CORS_ALLOW_ALL=true
EOF
mv "$TMP" "$ENV_FILE"

echo "worktree: $ROOT"
echo "  BACKEND_PORT=$BACKEND_PORT  FRONTEND_PORT=$FRONTEND_PORT  DOCS_PORT=$DOCS_PORT"
echo "  VITE_API_BASE=http://localhost:$BACKEND_PORT"
echo "  .env: $ENV_FILE"
echo "提示：若端口仍被占用（strictPort / fastapi 报错），调整占用方后重跑本脚本即可。"