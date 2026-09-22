# 施工多目标优化系统前端

基于 Vue 3 + Vite 的施工成本、工期、碳排放多目标优化系统前端应用。

## 项目简介

该软件用于获取施工数据（工序信息、资源使用情况），为施工策略优化提供参考。通过定义施工模式（工序成本、工期、碳排放之间的关系），使用 NSGA-II 算法进行多目标优化，并在前端进行帕累托解集的可视化展示。

## 核心功能

- **日报处理** - 导入施工日报，解析资源使用情况并分配到各工序
- **任务管理** - 工序信息管理、进度跟踪、前置依赖设置
- **进度管理** - 甘特图展示、关键路径计算、进度可视化
- **分析洞察** - NSGA-II 多目标优化、帕累托解集可视化
- **资源配置** - 资源分类管理、资源使用统计

## 技术栈

- **框架**: Vue 3.5 + Composition API
- **语言**: TypeScript 5.9
- **路由**: Vue Router 5.0
- **状态**: Pinia 3.0 + @pinia/colada
- **样式**: Tailwind CSS 4 + 自研玻璃组件层 (无 DaisyUI)
- **图标**: Material Symbols

## 开发命令

项目由 `vp` 管理（vite 封装），**禁止** 使用 npm/pnpm 命令：

```bash
vp dev             # 启动开发服务器
vp build           # 构建生产版本（含类型检查）
vp run build-only  # 仅构建，不进行类型检查
vp run type-check  # 类型检查
vp check --fix     # 代码检查 + 格式化 (oxlint + oxfmt)
vp run generate-api # 从 OpenAPI 生成客户端 (需后端运行)
```

## 项目结构

```
src/
├── pages/           # 页面组件 (file-based routing)
├── components/      # 通用与业务组件 (common/ui/schedule/resource/...)
├── composables/     # API 封装与共享逻辑
├── stores/          # Pinia 状态管理
├── types/           # TypeScript 类型定义
├── utils/           # 工具函数
└── assets/          # 全局样式 (base.css 主题 / components.css 组件层 / glass.css)
```

## 许可证

MIT
