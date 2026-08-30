import { defineConfig } from 'vite-plus'

// 仓库根配置：仅为 vite-plus 的 git hooks 提供 staged 路由。
// 钩子（core.hooksPath=frontend/.vite-hooks/_ 的 pre-commit → `vp staged`）以仓库根为 cwd
// 运行，须在根目录找到 vite.config.ts 才能读取 staged；格式化按文件侧别分发：
// frontend/* → oxlint/oxfmt（vp check --fix），backend/*.py → ruff（见 scripts/pre-commit-format.sh）。
export default defineConfig({
  staged: {
    '*': 'bash scripts/pre-commit-format.sh',
  },
})