"""FastAPI 应用入口(可运行骨架)。

- 挂 request_id 中间件与统一异常处理;
- GET /api/health:存活检查(8/29 验收门槛「项目可启动」的探针);
- 模型/任务等业务路由由成员2 后续工作包(WP02+)挂载。
"""
import logging
import os
import sys

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .core.config import get_settings
from .core.request_id import RequestIdMiddleware
from .core.response import ok, register_exception_handlers
from .routers import (
    admin_models,
    admin_users,
    api_key,
    auth,
    chat,
    models,
    open_api,
    stats,
    tasks,
    uploads,
    user,
)
from fastapi.middleware.cors import CORSMiddleware

def create_app() -> FastAPI:
    settings = get_settings()  # 必填环境变量缺失时在此抛出,启动即失败
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] request_id=%(message)s",
        stream=sys.stdout,
    )

    # CORS:默认仅 localhost/127.0.0.1;生产通过 CORS_ORIGINS 配置逗号分隔的白名单
    cors_pattern = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    extra_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    if extra_origins:
        escaped = "|".join(o.replace(".", r"\.").replace("://", "://") for o in extra_origins)
        cors_pattern = rf"({cors_pattern}|^({escaped})$)"

    app = FastAPI(title="AI 大模型门户", version="0.2.0", docs_url=f"{settings.api_prefix}/docs")
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=cors_pattern,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)

    @app.get(f"{settings.api_prefix}/health")
    async def health():
        """存活探针:供 Nginx/Supervisor 与每日集成验收使用。"""
        return ok(data={"status": "up", "service": "ai-portal-backend"})

    # 所有上传和模型生成的本地产物均通过同一绝对目录暴露,避免运行目录不同导致 404。
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(settings.upload_path)), name="static")

    app.include_router(auth.router, prefix=settings.api_prefix)
    app.include_router(user.router, prefix=settings.api_prefix)
    app.include_router(admin_users.router, prefix=settings.api_prefix)
    from .routers import admin_wallet
    app.include_router(admin_wallet.router, prefix=settings.api_prefix)
    for prefix in (settings.api_prefix, "/api/v1"):
        app.include_router(models.router, prefix=prefix)
        app.include_router(admin_models.router, prefix=prefix)
        app.include_router(chat.router, prefix=prefix)
        app.include_router(tasks.router, prefix=prefix)
        app.include_router(uploads.router, prefix=prefix)
        app.include_router(stats.router, prefix=prefix)
    # open_api 自带 /v1/chat/completions 别名，只挂一次可避免 /api/v1 路径重复。
    app.include_router(open_api.router, prefix=settings.api_prefix)
    from .routers import wallet
    from .routers import api_key
    from .routers import auth_sms
    # 钱包/开放平台 Key/短信认证 路由同样统一走 settings.api_prefix,保持外部 URL 不变
    app.include_router(wallet.router, prefix=settings.api_prefix)
    app.include_router(api_key.router, prefix=settings.api_prefix)
    app.include_router(auth_sms.router, prefix=settings.api_prefix)
    return app


app = create_app()

# 测试
if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
