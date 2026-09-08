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
legacy/*      合并前各仓库历史（legacy/backend、legacy/frontend、legacy/rust-server）
              考古保留，不入 main；如需继续 Rust 版开发，从 legacy/rust-server 开分支
```

## Agent 执行原则（重要）

- **钩子默认可靠**：所有契约快照的导出与校验均由 Git 钩子自动完成，**agent 无需手动运行 `openapi-export.sh` 或 `check-contract.sh`**，除非钩子明确报错或被跳过。
- **线性流程**：正常开发遵循下方“契约变更 checklist”的简化步骤，无分支、无额外验证。
- **异常才手动**：仅当出现钩子失败、使用 `--no-verify` 跳过钩子、或怀疑环境未初始化时，才需要手动执行 `check-contract.sh` 或 `toolchain-sync.sh` 排查。

## Git 规则

1. **通过 git rebase 消除重复**：feature 分支开发时先 `git rebase main`，保持分支线性、无重复提交。
2. **使用 ff-only 合并到 main**：合并走 `git merge --ff-only`，main 始终线性推进（除非特别要求，否则先不要 rebase&merge）。
3. **一次前后端协调 = 一个 commit**：后端契约变更与**配套前端代码**（以及重新生成客户端所需的快照 `openapi.json`）必须在**同一个 commit** 中出现。
4. **合并/推送 main 前**：正常情况下钩子已保证契约一致，无需额外检查；若合并或 rebase 过程中出现异常（如钩子未运行、冲突解决后未自动重导出），手动执行 `bash scripts/check-contract.sh` 确认快照与后端代码一致、客户端可离线再生。
5. 推送 main 始终 fast-forward；需改写历史时用 `--force-with-lease`，并先与使用相关 worktree 的人确认。

### Git 钩子（自愈机制）

> **Agent 无需关心以下钩子的具体触发细节**，它们会在合适的时机自动运行。仅当钩子报错或未生效时，才需根据提示手动处理。

| 钩子         | 触发                                         | 动作                                                                                                                                               | 失败时                                                |
| ------------ | -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------- |
| pre-commit   | 每次提交                                     | 自动格式化（`vp staged` + `scripts/pre-commit-format.sh`）后，若暂存含 `backend/src/**` 自动重导出 `openapi.json` 并 `git add`，快照随本次提交入库 | venv 缺失 → warn+skip（后续可用 check-contract 兜底） |
| post-merge   | merge / pull 成功                            | `pnpm-lock.yaml` / `uv.lock` 变化 → 自动 `vp install` / `uv sync --all-groups`；`backend/src` 或快照变化 → 重导出核对                              | 只打印告警，不阻塞                                    |
| post-rewrite | rebase / `commit --amend` / cherry-pick 成功 | 同上（对照改写前 tip）                                                                                                                             | 同上                                                  |

> 冲突中止的 merge/rebase **不触发** post 钩子——解决冲突后，下一次 commit 的 pre-commit 会自动重导出快照，无需额外手动操作。

## 契约变更 checklist（后端 OpenAPI 有改动时）

**正常流程（无分支）**：

1. 修改后端 schema / router / service；
2. 如前端需要适配，修改前端代码（客户端生成可选：若需要本地类型提示，运行 `bash scripts/gen-client.sh`，否则提交后由钩子处理）；
3. 提交——pre-commit 钩子会自动重导出 `openapi.json` 并包含在本次提交中。

**异常处理**（仅在以下情况手动介入）：

- 钩子报告失败或被 `--no-verify` 跳过 → 运行 `bash scripts/check-contract.sh` 验证一致性；
- 怀疑环境未初始化（如钩子未安装）→ 运行 `bash scripts/toolchain-sync.sh` 初始化后重新提交。

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

| 命令                                                         | 说明                                                                         |
| ------------------------------------------------------------ | ---------------------------------------------------------------------------- |
| `scripts/worktree-env.sh`                                    | 为当前 worktree 分配端口并写根 `.env`（幂等，保留 DATABASE_URL 等既有键）    |
| `scripts/worktree-bootstrap.sh`                              | 新 worktree 一键引导（env + 依赖 + 客户端 + 类型检查）                       |
| `scripts/dev-backend.sh` / `dev-frontend.sh` / `dev-docs.sh` | 三端启动                                                                     |
| `scripts/gen-client.sh`                                      | 快照 → 前端客户端（离线，**仅在需要本地类型提示时手动运行**）                |
| `scripts/check-contract.sh`                                  | 契约一致性校验（**异常时手动运行**，正常情况下由钩子自动保证）               |
| `scripts/openapi-export.sh`                                  | 后端代码 → 根 `openapi.json`（**通常由 pre-commit 自动调用**，手动仅调试用） |
| `scripts/toolchain-sync.sh`                                  | 初始化或修复钩子、依赖、快照（**怀疑环境未初始化时运行**）                   |

### 常见坑

- **端口被占**：vite 已设 `strictPort`，后端端口冲突直接报错——调整占用方后重跑 `scripts/worktree-env.sh`；不要静默自增端口（会导致配对漂移）。
- **CORS**：dev 默认**同源**——浏览器只访问前端端口的 `/api`（vite 反代到本 worktree 后端），不触发 CORS；`CORS_ALLOW_ALL=true` 仅在跨机直连（如手机/局域网直接访问后端端口）时才需要。注意 `allow_origins=["*"]` 时浏览器强制禁止携带凭据（`allow_credentials=False`）；引入认证后改用 `CORS_ORIGINS` 白名单。
- **`vp preview`（4173）无反代**：`/api` 请求会 404，dev 反代仅存在于 `scripts/dev-frontend.sh` 启动的开发服务器；部署环境由 nginx `/api` 反代提供。
- **共享数据库**：默认各 worktree 共用主 worktree 的 `DATABASE_URL`。改迁移/数据的 agent 应在自己 worktree 的 `.env` 配独立库名（如 `cctv2-wt2`）并执行 `alembic upgrade head`。
- **钩子未生效**：若提交时未自动重导出快照，或合并后依赖未更新，通常因为 `vp install` 未运行或 `core.hooksPath` 未设置。运行 `bash scripts/toolchain-sync.sh` 修复即可，无需重复手动校验。
- **权限不足**：`vp add`, `uv sync`, `git commit` 等命令需要写公共目录或主 worktree 目录时，请求更高权限运行即可。
- **前端不要直接改 `src/client/`**：改后端契约请走上方 checklist。
