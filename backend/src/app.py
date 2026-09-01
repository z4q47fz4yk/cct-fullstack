import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from src.routers import (
    auth,
    chart,
    daily_report,
    diagnostics,
    evaluation,
    measure,
    optimize,
    plan,
    progress,
    project,
    resource,
    resource_public,
    resource_usage,
    tag,
    task,
    weather,
)

from .config import settings
from .database import engine
from .services.optimization_consumer import recover_stale_runs

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时回收上次进程遗留的优化运行。

    后台任务（引擎线程、事件消费者）随进程退出而丢失，遗留的
    PENDING/RUNNING 运行不可能再被推进，标记为失败避免永久悬挂。
    DB 不可用时仅记日志，不阻塞应用启动。
    """
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            recovered = await recover_stale_runs(session)
            if recovered > 0:
                logger.info("启动回收遗留优化运行 %d 条（标记为失败）", recovered)
    except Exception:
        logger.exception("启动回收遗留优化运行失败")
    yield


app = FastAPI(
    title=settings.app_name,
    generate_unique_id_function=lambda route: route.name.removesuffix("_endpoint"),
    lifespan=lifespan,
)
app.include_router(auth.router)
app.include_router(project.router)
app.include_router(task.router)
app.include_router(resource.router)
app.include_router(resource_public.router)
app.include_router(resource_usage.router)
app.include_router(daily_report.router)
app.include_router(optimize.router)
app.include_router(tag.router)
app.include_router(chart.router)
app.include_router(plan.router)
app.include_router(measure.router)
app.include_router(progress.router)
app.include_router(weather.router)
app.include_router(evaluation.router)
app.include_router(diagnostics.router)

# CORS 由环境变量控制（backend/src/config.py 的 Settings.cors_mode）：
# - CORS_ALLOW_ALL=true（多 worktree 开发默认，见仓库根 .env / scripts/worktree-env.sh）
#   允许任意来源跨域，适配前端端口变化；此时 allow_credentials=False（dev 同源 /api
#   反代不涉及跨域凭据，认证 Cookie 正常；跨机直连须改 CORS_ORIGINS 白名单）；
# - 否则按 CORS_ORIGINS 白名单（默认 localhost:5173/5174/5175/4173）。
allow_origins, allow_credentials = settings.cors_mode()
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 签名 Cookie 会话（Starlette SessionMiddleware）：
# - 签名（itsdangerous）而非加密：仅存最小身份 user_id + 瞬态 OIDC state，不含敏感数据；
# - SameSite=Lax 是 OIDC 回调导航携带 Cookie 的前提（勿改 strict）；
# - cookie path 限定 /api（浏览器侧 API 请求均带 /api 前缀），与前端 Cookie 隔离；
# - 生产 https_only=True（debug 关闭时自动开启）。
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key,
    session_cookie=settings.session_cookie_name,
    max_age=settings.session_max_age,
    path=settings.session_cookie_path,
    same_site="lax",
    https_only=settings.session_cookie_secure,
)

if settings.auth_required:
    # 全局登录门槛（AUTH_REQUIRED=true 时启用）：除公开路径外一律要求有效会话。
    # 默认关闭：业务路由保持开放，既有行为与测试不受影响；
    # 启用后由前端 401 拦截跳登录页。
    _PUBLIC_PREFIXES = ("/auth/", "/docs", "/redoc", "/openapi.json")

    @app.middleware("http")
    async def auth_gate_middleware(request: Request, call_next):
        path = request.url.path
        if (
            not path.startswith(_PUBLIC_PREFIXES)
            and request.session.get("user_id") is None
        ):
            return JSONResponse(status_code=401, content={"detail": "未登录"})
        return await call_next(request)


@app.exception_handler(Exception)
async def global_exception_handler(req: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        headers={"Access-Control-Allow-Origin": "*"},
        content={"detail": "服务器错误，请联系管理员"},
    )
