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
from .routers import admin_models, api_key, auth, chat, models, open_api, stats, tasks, uploads
from fastapi.middleware.cors import CORSMiddleware


def create_app() -> FastAPI:
    settings = get_settings()  # 必填环境变量缺失时在此抛出,启动即失败
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] request_id=%(message)s",
        stream=sys.stdout,
    )

    app = FastAPI(title="AI 大模型门户", version="0.2.0", docs_url=f"{settings.api_prefix}/docs")
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
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

    os.makedirs(settings.upload_dir, exist_ok=True)
    app.mount("/static", StaticFiles(directory=settings.upload_dir), name="static")

    app.include_router(auth.router, prefix=settings.api_prefix)
    for prefix in (settings.api_prefix, "/api/v1"):
        app.include_router(models.router, prefix=prefix)
        app.include_router(admin_models.router, prefix=prefix)
        app.include_router(chat.router, prefix=prefix)
        app.include_router(tasks.router, prefix=prefix)
        app.include_router(open_api.router, prefix=prefix)
        app.include_router(uploads.router, prefix=prefix)
        app.include_router(stats.router, prefix=prefix)
    from .routers import wallet
    app.include_router(wallet.router)
    app.include_router(api_key.router)
    return app


app = create_app()

# 测试
if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000)
