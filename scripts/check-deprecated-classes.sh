#!/usr/bin/env bash
# 检查 Vue 模板中的废弃组件层类名（DaisyUI 兼容层的历史残留），防止旧类名重新混入。
#
# 废弃类清单以本脚本为唯一事实来源；pre-commit 钩子（scripts/pre-commit-format.sh）
# 会对暂存的 .vue 文件自动执行，也可手动全量扫描：
#   bash scripts/check-deprecated-classes.sh            # 全量扫描 frontend/src
#   bash scripts/check-deprecated-classes.sh <files>    # 只检查指定文件（已删除的文件自动跳过）
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"

# 废弃类名 → 替代方案（新增废弃类时在此登记，钩子即自动生效）
DEPRECATED=(
  "form-control:使用 fieldset"
  "label-text:使用 fieldset-legend 或纯文本 span"
  "label-text-alt:使用 label.label 或描述性段落"
)

# 收集目标文件
FILES=()
if [ "$#" -gt 0 ]; then
  for f in "$@"; do
    [ -f "$f" ] && FILES+=("$f")
  done
else
  while IFS= read -r -d '' f; do
    FILES+=("$f")
  done < <(find "$ROOT/frontend/src" -name "*.vue" -print0)
fi

if [ "${#FILES[@]}" -eq 0 ]; then
  echo "废弃类名检查：无待检查文件"
  exit 0
fi

hits=0
for f in "${FILES[@]}"; do
  for item in "${DEPRECATED[@]}"; do
    name="${item%%:*}"
    replacement="${item#*:}"
    # 只匹配静态 class="..." 属性；类名后必须是空白或引号（避免 label-text 误中 label-text-alt）
    while IFS= read -r line; do
      line_no="${line%%:*}"
      echo "$f:$line_no: 使用了已废弃类名 '$name' → 改用：$replacement"
      hits=$((hits + 1))
    done < <(grep -nE "class=\"[^\"]*${name}([ \"]|$)" "$f" || true)
  done
done

if [ "$hits" -gt 0 ]; then
  echo "检测到 $hits 处废弃类名（见上），请改用替代方案后重新提交。" >&2
  exit 1
fi
echo "废弃类名检查通过"