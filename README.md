# CCT 施工多目标优化平台（单仓库）

前后端合并为单一仓库：一次前后端协调 = 一个 commit（后端代码 + `openapi.json` 契约快照 + 配套前端代码）。

```
frontend/   Vue 3 + Vite 前端（见 frontend/AGENTS.md）
backend/    FastAPI + SQLModel 后端（见 backend/AGENTS.md）
scripts/    多 worktree 开发工具（端口分配、启动、契约校验）
openapi.json 后端契约快照（入库，前端客户端离线生成源）
```

## 快速上手（主 worktree）

```bash
# 后端：安装依赖 → 启动（默认 8000）
cd backend && uv sync --all-groups
bash ../scripts/dev-backend.sh

# 前端：安装依赖 → 生成客户端 → 启动（默认 5173）
cd frontend && vp install
bash ../scripts/gen-client.sh
bash ../scripts/dev-frontend.sh

# 文档站（可选，默认 5174）
bash ../scripts/dev-docs.sh
```

无 `.env` 时使用默认端口：前端 5173、后端 8000、docs 5174。

## 多 worktree 并行开发

每个 worktree 拥有独立的端口三元组，写入**仓库根 `.env`**（已 gitignore），
前后端共用同一份 ⇒ 前端永远访问自己 worktree 的后端，端口一一对应：

```bash
git worktree add ../cct-wt2 -b feat/xxx
cd ../cct-wt2
bash scripts/worktree-bootstrap.sh   # 分配端口 + 同步依赖 + 生成客户端 + 类型检查
bash scripts/dev-backend.sh          # 自动使用该 worktree 的后端端口
bash scripts/dev-frontend.sh         # 自动使用该 worktree 的前端端口
```

详见根 `AGENTS.md`（Git 规则、契约变更 checklist、常见坑）。

## 契约变更（后端 OpenAPI 有改动的标准流程）

```bash
bash scripts/openapi-export.sh    # 后端代码 → 根 openapi.json
bash scripts/gen-client.sh        # 快照 → 前端客户端（离线）
bash scripts/check-contract.sh    # 校验契约与快照一致、客户端可离线再生
# 提交：后端代码 + openapi.json + 配套前端代码，一个 commit
```

改后端 schema 而未同步快照时，`scripts/check-contract.sh` 会在合并到 main 前拦下漂移。