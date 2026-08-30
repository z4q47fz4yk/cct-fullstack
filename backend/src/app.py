import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.middleware.cors import CORSMiddleware

from src.routers import (
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://localhost:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(req: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        headers={"Access-Control-Allow-Origin": "*"},
        content={"detail": "服务器错误，请联系管理员"},
    )
