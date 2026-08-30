# 快速开始

本文介绍如何在一台机器上把整套软件跑起来，并完成第一个"项目 → 工序 → 资源 → 优化"的完整流程。

## 架构一览

CCT 由两部分组成：

```
┌─────────────────────┐       ┌──────────────────────┐
│  前端 vite-project   │  HTTP │  后端 backendv2       │
│  Vue 3 + VitePress   │ ─────▶│  FastAPI + PostgreSQL│
│  http://localhost:5173 │      │  http://localhost:8000 │
└─────────────────────┘       └──────────────────────┘
```

## 环境要求

| 组件       | 要求                  | 说明                                        |
| ---------- | --------------------- | ------------------------------------------- |
| Python     | ≥ 3.14                | 后端运行时                                  |
| uv         | 最新                  | Python 包管理（官方推荐，项目使用 uv.lock） |
| PostgreSQL | 14+                   | 数据库，需支持 asyncpg 驱动                 |
| Node.js    | ^20.19.0 或 ≥ 22.12.0 | 前端运行时                                  |
| pnpm       | 11.x                  | 前端包管理（经 `vp` 封装调用）              |

::: tip
前端项目由 `vp`（vite-plus 封装）统一管理，**禁止**直接使用 `npm` / `pnpm` 命令安装依赖，请使用 `vp` 提供的命令（见下文）。
:::

## 第一步：启动后端

```bash
cd backendv2

# 1. 安装依赖
uv sync

# 2. 创建数据库（首次）
psql -U postgres -c "CREATE DATABASE cctv2;"

# 3. 配置数据库连接（backendv2/.env）
# DATABASE_URL=postgresql+asyncpg://cct:cct@localhost:5432/cctv2

# 4. 执行数据库迁移
uv run --group migrate alembic upgrade head

# 5. 启动服务（开发模式，热重载）
uv run uvicorn src.app:app --reload --reload-dir src
```

后端启动后：

- API 文档（Swagger UI）：<http://localhost:8000/docs>
- OpenAPI 规范：<http://localhost:8000/openapi.json>

## 第二步：启动前端与文档站

```bash
cd vite-project

# 安装依赖（首次）
vp install

# 启动开发服务器（应用，端口 5173）
vp dev

# 另开一个终端：启动文档站开发服务器（端口 5174）
vp run docs:dev
```

应用启动后访问 <http://localhost:5173>。应用与文档站**同源部署**：

- 应用页面：<http://localhost:5173/>
- 文档站：<http://localhost:5173/docs/>（应用 dev server 将 `/docs` 代理到 5174 的 VitePress）
- 文档站独立访问：<http://localhost:5174/>

应用左上角导航栏与文档站导航栏均有对方入口（「文档」/「打开系统」），可互相跳转。

::: tip
前端通过 `src/hey-api.ts` 中的 `baseUrl: 'http://localhost:8000'` 访问后端，如后端部署在其他地址，请修改该文件。
:::

## 第三步：走通第一个完整流程

### 1. 创建项目

打开首页（<http://localhost:5173>），点击「新建项目」，输入项目名称（如"某商业综合体项目"）并保存。

### 2. 建立工序

进入项目 → 「任务管理」，点击右下角添加按钮创建工序，例如：

| 任务编码 | 任务名称 | 工期（天） | 前置任务 |
| -------- | -------- | ---------- | -------- |
| AUTO-1   | 基坑开挖 | 10         | -        |
| AUTO-2   | 基础施工 | 15         | AUTO-1   |
| AUTO-3   | 主体结构 | 30         | AUTO-2   |

> 任务编码由系统自动生成（AUTO-N），无需手动填写。前置任务决定施工顺序，也决定了关键路径与总工期。

### 3. 配置资源

进入项目 → 设置 → 资源管理，创建资源并填写**单价**与**碳排放因子**，例如：

| 资源名称       | 类别 | 单位 | 单价（元） | 碳排放因子（kg/单位） |
| -------------- | ---- | ---- | ---------- | --------------------- |
| 泥工           | 人工 | 工日 | 300        | 2.0                   |
| 挖掘机         | 机械 | 台班 | 1500       | 50.0                  |
| 商品混凝土 C30 | 材料 | m³   | 480        | 320.0                 |

也可以使用「从公共资源导入」直接复制内置资源字典中的条目。

### 4. 录入资源使用

两种方式任选：

- **手动录入**：进入「资源使用录入」，选择日期、工序、资源与数量保存；
- **导入日报**：进入「日报处理」，上传施工日报 Excel（格式见[日报处理](/usage/daily-report)章节）。

### 5. 运行优化

进入「分析洞察 → 优化结果」，配置优化参数（种群大小、代数等），点击「开始优化」。等待运行完成后即可看到帕累托前沿三维图与解集表格。

### 6. 查看碳排放

进入「设置 → 碳排放总览」查看项目碳排放概况；配置「碳排放标签」与「碳排放图表」后，可在「分析洞察 → 碳排放分析」中查看按标签拆解的饼图。

## 开发命令速查

### 后端

```bash
uv run uvicorn src.app:app --reload --reload-dir src   # 启动开发服务
uv run pytest                                           # 运行测试
uv run ruff check .                                     # 代码检查
uv run --group migrate alembic upgrade head             # 数据库迁移
```

### 前端

```bash
vp dev            # 启动开发服务器
vp build          # 构建生产版本（含类型检查）
vpr build-only    # 仅构建，不进行类型检查
vp check --fix    # 代码检查 + 格式化
vpr generate-api  # 从后端 OpenAPI 生成 API 客户端（需后端运行）
```

### 文档站

```bash
vp run docs:dev      # 启动文档站开发服务器（http://localhost:5174，应用 /docs 代理指向它）
vp run docs:build    # 构建文档站（产物带 /docs/ base 前缀，输出到 docs/.vitepress/dist）
vp run docs:preview  # 预览构建产物
```

## 部署（L1 同源双构建）

应用与文档站部署到**同一域名**下：应用占 `/`，文档站占 `/docs/`（VitePress 已配置 `base: '/docs/'`，构建产物中所有资源路径自动带前缀）。

### 方式一：合并静态目录

```bash
# 构建应用
vp build                     # 产物在 dist/
# 构建文档站
vp run docs:build            # 产物在 docs/.vitepress/dist/

# 部署：把文档产物拷入应用产物目录的 docs/ 子目录
cp -r docs/.vitepress/dist docs-dist
mkdir -p dist/docs && cp -r docs-dist/* dist/docs/
# 之后将 dist/ 整体发布到静态服务器
```

注意合并时文档产物应**先拷入**、应用产物**后覆盖**（避免 emptyOutDir 清掉 docs/）。

### 方式二：服务器 rewrite

用 nginx 等把 `/docs/*` 指到文档产物，其余路径走应用 SPA：

```nginx
# 应用是 history 路由：必须 SPA fallback 到 index.html，且不能吞掉 /docs/*
location /docs/ {
    alias /var/www/docs/;
    try_files $uri $uri.html $uri/ =404;   # 文档站已开 cleanUrls
}
location / {
    root /var/www/app;
    try_files $uri /index.html;            # SPA fallback
}
```

::: warning

- 应用为 history 路由，**必须有 SPA fallback**，且规则顺序上 `/docs/` 不能落入 SPA fallback；
- 文档站已开启 `cleanUrls`，服务器需支持 `/foo` → `foo.html` 的映射（或按方式一直接输出目录）。
  :::

### 跨站链接约定

- 应用 → 文档：使用 `docsHref('/guide/intro')`（`site.config.ts`），如应用导航栏的「文档」入口；
- 文档 → 应用：Markdown 中使用 `<AppLink to="/project/1">` 组件（自定义主题已注册），或在导航栏点击「打开系统」；
- 文档站导航/侧边栏中**不要**直接写应用路径——会被 VitePress `withBase` 加上 `/docs/` 前缀，请使用 `<AppLink>`；
- 应用跳转文档时可在 URL 带 `?projectId=123`，文档页用 `<BackToProject>` 组件渲染「回到项目」链接。
