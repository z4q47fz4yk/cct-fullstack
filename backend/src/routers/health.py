"""服务能力探测（health）路由。

对外端点（挂载于根路径，公共 URL 前缀 /api 由反代剥离）：
- ``GET /health``：返回后端启用状态。

该端点用于前端在应用启动时**一次性**探测后端能力：
- ``auth_enabled``：是否启用登录认证（OIDC Provider 已配置且 AUTH_REQUIRED）；
- ``ai_enabled``：是否启用 AI 对话（PI_ENABLED）。

调用方拿到结果后据此**动态注册**前端路由（见 vue-router 动态路由）。
未配置某能力时，前端不应让用户看到对应入口；即便通过 URL 直接访问，
由于该路由未被注册，vue-router 会走到 404 兜底页。

未携带凭据也可调用，不受全局登录门槛限制（位于 _PUBLIC_PREFIXES 中）。
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from src.config import settings

router = APIRouter(tags=["health"])


class HealthResp(BaseModel):
    """健康检查响应体。

    - ``auth_enabled``：系统是否启用了登录功能（OIDC Provider 已配置）。
      与 ``auth_required``（全局登录门槛）不同：即使未强制全站登录，
      只要配了 Provider 即视为具备登录能力，前端可以展示登录入口。
    - ``ai_enabled``：是否启用 AI 对话（``PI_ENABLED``）。关闭时
      ``/ai/chat`` 会返回 503，前端不应暴露 AI 相关入口。
    """

    auth_enabled: bool
    ai_enabled: bool


@router.get("/health", summary="服务能力探测", response_model=HealthResp)
async def health_endpoint() -> HealthResp:
    """返回后端启用状态：前端据此动态注册登录 / AI 相关路由。

    该端点**始终可访问**（公共路径，未启用登录时也不需要凭据），
    用于前端一次性探测后端能力。
    """
    # 登录能力判定：OIDC Provider 非空即视为启用。
    # auth_required 是"全局是否拦截未登录访问"的开关，不影响"是否能登录"。
    auth_enabled = len(settings.oidc_providers) > 0
    return HealthResp(
        auth_enabled=auth_enabled,
        ai_enabled=settings.pi_enabled,
    )
