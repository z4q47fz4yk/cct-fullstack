# CCT 施工多目标优化平台（单仓库）

这是一个前后端分离项目，`frontend/` 与 `backend/` 合并为**单一仓库**：
**一次前后端协调 = 一个 commit**（后端代码 + `openapi.json` 契约快照 + 配套的前端代码）。

多 agent 多 worktree 并行开发时，每个 worktree 拥有独立的端口三元组（前端/后端/docs），
由**仓库根 `.env`**（自动生成、gitignore）统一管理；前后端共用同一份 `.env`，
前端永远访问自己 worktree 的后端，端口一一对应。

## 仓库布局

```
frontend/     Vue 3 + Vite 前端（详见 frontend/AGENTS.md）
backend/      FastAPI + SQLModel 后端（详见 backend/AGENTS.md）
scripts/      多 worktree 开发工具（端口分配、启动、契约校验）
openapi.json  后端契约快照（入库；前端客户端离线生成源）
```

## Git 规则

1. **通过 git rebase 消除重复**：feature 分支开发时先 `git rebase main`，保持分支线性、无重复提交。
2. **使用 ff-only 合并到 main**：合并走 `git merge --ff-only`，main 始终线性推进。
3. **一次前后端协调 = 一个 commit**：后端契约变更与**配套前端代码**（以及重新生成客户端所需的快照 `openapi.json`）必须在**同一个 commit** 中出现。
4. **合并/推送 main 前必检**：rebase / merge 冲突解决后运行 `bash scripts/check-contract.sh`（快照可能被 3-way 合并或手工解析改写；commit 时的快照已由 pre-commit 钩子自动维护，见下）。
5. 推送 main 始终 fast-forward；需改写历史时用 `--force-with-lease`，并先与使用相关 worktree 的人确认。

### Git 钩子（自愈机制）

| 钩子 | 触发 | 动作 | 失败时 |
| --- | --- | --- | --- |
| pre-commit（`frontend/.vite-hooks/pre-commit` = `vp staged` + `scripts/pre-commit-contract.sh`） | 每次提交 | `vp staged` 格式化分发（`scripts/pre-commit-format.sh`）后，若暂存含 `backend/src/**` 自动 `openapi-export.sh` + `git add openapi.json`，快照随本次提交入库 | venv 缺失 → warn+skip（check-contract 兜底） |
| post-merge（`frontend/.vite-hooks/post-merge`） | merge / pull 成功 | `pnpm-lock.yaml` / `uv.lock` 变化 → 自动 `vp install` / `uv sync --all-groups`；`backend/src` 或快照变化 → 重导出核对 | 只打印告警，不阻塞 |
| post-rewrite（`frontend/.vite-hooks/post-rewrite`） | rebase / `commit --amend` / cherry-pick 成功 | 同上（对照改写前 tip） | 同上 |

> 钩子运行文件（`frontend/.vite-hooks/post-merge`、`post-rewrite`）**入库**；底层 `_/` stub 与
> `core.hooksPath` 由本地 `vp install` 安装（见 frontend/.vite-hooks）。冲突中止的 merge/rebase
> **不触发** post 钩子——解决冲突后重导出的职责落在下一次 commit 的 pre-commit 与合并前的 check-contract。

## 契约变更 checklist（后端 OpenAPI 有改动时）

1. 修改后端 schema / router / service；
2. ~~`bash scripts/openapi-export.sh`~~ —— **pre-commit 钩子已自动执行**（改动 `backend/src` 时），手工执行为可选；
3. `bash scripts/gen-client.sh` —— 快照 → 前端客户端（**离线**，无需运行后端）；
4. `bash scripts/check-contract.sh` —— **rebase/冲突解决后、合并/推送 main 前**校验快照与后端代码一致、客户端可离线再生；
5. 前端代码据此适配；
6. **一个 commit** 提交：后端代码 + `openapi.json` + 前端代码。

> `frontend/src/client/` **不入库**（gitignore），由每个 worktree 从入库的 `openapi.json` 离线生成；
> 严禁手工修改 `frontend/src/client/`。改契约请走上面的 checklist，不要直接改生成物。

## 多 worktree 开发

每个 worktree = 一份完整仓库 + 一份独立的根 `.env`（已 gitignore）。
`.env` 由 `scripts/worktree-env.sh` 自动生成/更新，前后端/docs 共用 ⇒ 端口一一对应：

| worktree                 | 前端 `FRONTEND_PORT` | 后端 `BACKEND_PORT` | docs `DOCS_PORT` |
| ------------------------ | -------------------- | ------------------- | ---------------- |
| main（无 `.env` 时默认） | 5173                 | 8000                | 5174             |
| 其他（自动分配首个空闲） | 5174+                | 8001+               | 5175+            |

`.env` 关键变量：

| 变量             | 用途                                                                                                                   |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `BACKEND_PORT`   | 后端 dev server 端口（`fastapi dev --port`）                                                                           |
| `FRONTEND_PORT`  | 前端 dev server 端口（vite，`strictPort` 冲突即报错）                                                                  |
| `DOCS_PORT`      | 文档站 vitepress 端口（前端 `/docs` 代理指向它）                                                                       |
| `VITE_API_BASE`  | 前端访问后端的基址 = `/api`（dev 由 vite 反代到 `BACKEND_PORT`，部署由 nginx 反代；跨机直连可改为 `http://host:port`） |
| `CORS_ALLOW_ALL` | 开发期放开 CORS 允许任意来源（此时 `allow_credentials=False`）                                                         |
| `DATABASE_URL`   | 沿用主 worktree 的已有值；迁移/数据类 agent 建议独立库名                                                               |

### 新建 worktree

```bash
git worktree add ../cct-wt2 -b feat/xxx   # zed 环境会自动触发 bootstrap
cd ../cct-wt2
bash scripts/worktree-bootstrap.sh        # 分配端口 + uv sync + vp install + 离线生成客户端 + 类型检查
bash scripts/dev-backend.sh               # 用 BACKEND_PORT 启动后端
bash scripts/dev-frontend.sh              # 用 FRONTEND_PORT 启动前端
bash scripts/dev-docs.sh                  # 用 DOCS_PORT 启动文档站（可选）
```

### 常用命令速查

| 命令                                                         | 说明                                                                                                                            |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------- |
| `scripts/worktree-env.sh`                                    | 为当前 worktree 分配端口并写根 `.env`（幂等，保留 DATABASE_URL 等既有键）                                                       |
| `scripts/worktree-bootstrap.sh`                              | 新 worktree 一键引导（env + 依赖 + 客户端 + 类型检查）                                                                          |
| `scripts/dev-backend.sh` / `dev-frontend.sh` / `dev-docs.sh` | 三端启动                                                                                                                        |
| `scripts/openapi-export.sh`                                  | 后端代码 → 根 `openapi.json`                                                                                                    |
| `scripts/gen-client.sh`                                      | 快照 → 前端客户端（离线）                                                                                                       |
| `scripts/check-contract.sh`                                  | 契约一致性校验（rebase/冲突解决后、合并/推送 main 前）                                                                               |
| `frontend/.vite-hooks/pre-commit` + `scripts/pre-commit-format.sh` / `scripts/pre-commit-contract.sh` | pre-commit 链：frontend/* → oxfmt，backend/*.py → ruff；暂存 backend/src 时自动重导出 openapi.json 并入提交                                        |
| `frontend/.vite-hooks/post-merge` / `post-rewrite`           | post 钩子：merge/rebase/amend 后自动装依赖（锁变化）并核对契约快照（共享逻辑在 scripts/toolchain-sync.sh）                            |

### 常见坑

- **端口被占**：vite 已设 `strictPort`，后端端口冲突直接报错——调整占用方后重跑 `scripts/worktree-env.sh`；不要静默自增端口（会导致配对漂移）。
- **CORS**：dev 默认**同源**——浏览器只访问前端端口的 `/api`（vite 反代到本 worktree 后端），不触发 CORS；`CORS_ALLOW_ALL=true` 仅在跨机直连（如手机/局域网直接访问后端端口）时才需要。注意 `allow_origins=["*"]` 时浏览器强制禁止携带凭据（`allow_credentials=False`）；引入认证后改用 `CORS_ORIGINS` 白名单。
- **`vp preview`（4173）无反代**：`/api` 请求会 404，dev 反代仅存在于 `scripts/dev-frontend.sh` 启动的开发服务器；部署环境由 nginx `/api` 反代提供。
- **共享数据库**：默认各 worktree 共用主 worktree 的 `DATABASE_URL`。改迁移/数据的 agent 应在自己 worktree 的 `.env` 配独立库名（如 `cctv2-wt2`）并执行 `alembic upgrade head`。
- **merge/rebase 后自动同步**：post-merge / post-rewrite 钩子负责在锁文件或后端代码变化后自动装依赖、核对快照。若钩子未生效（如 `vp install` 未运行、`core.hooksPath` 未设置），手动补 `bash scripts/toolchain-sync.sh <旧SHA>` 即可；冲突中止的 merge/rebase 不触发钩子，解决后靠下一次 commit 的 pre-commit 与 check-contract 兜底。
- **权限不足**：`vp add`, `uv sync`, `git commit` 等命令需要写公共目录或主 worktree 目录时，请求更高权限运行即可。
- **前端不要直接改 `src/client/`**：改后端契约请走上方 checklist。
