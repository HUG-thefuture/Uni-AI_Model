"""FastAPI 应用入口(可运行骨架)。

- 挂 request_id 中间件与统一异常处理;
- GET /api/health:存活检查(8/29 验收门槛「项目可启动」的探针);
- 模型/任务等业务路由由成员2 后续工作包(WP02+)挂载。
"""
import logging
import sys
import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.request_id import RequestIdMiddleware
from app.core.response import ok, register_exception_handlers
from app.bootstrap import startup_initialize


from app.routers import (admin_models, admin_users, admin_wallet, api_key, auth, chat, models,
                         open_api, stats, tasks, uploads, user, wallet)

from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(_: FastAPI):
    """在线程中执行同步初始化，避免阻塞应用事件循环。"""
    await asyncio.to_thread(startup_initialize)
    yield


def create_app() -> FastAPI:
    settings = get_settings()  # 必填环境变量缺失时在此抛出,启动即失败
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] request_id=%(message)s",
        stream=sys.stdout,
    )

    app = FastAPI(
        title="AI 大模型门户", version="0.1.0",
        docs_url=f"{settings.api_prefix}/docs", lifespan=lifespan,
    )
    # 所有上传和模型生成的本地产物均通过同一绝对目录暴露，避免运行目录不同导致 404。
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(settings.upload_path)), name="static")
    #CORS:前后端分离联调
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "null",  # file:// 方式打开前端时浏览器发送 Origin: null
            "http://127.0.0.1:63342",
            "http://localhost:63342",
            "http://127.0.0.1:4174",
            "http://localhost:4174",
        ],
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

    # 注册接口:POST /api/auth/register
    app.include_router(auth.router, prefix=settings.api_prefix)
    app.include_router(wallet.router, prefix=settings.api_prefix)
    app.include_router(stats.router, prefix=settings.api_prefix)
    app.include_router(user.router, prefix=settings.api_prefix)
    app.include_router(api_key.router, prefix=settings.api_prefix)

    app.include_router(admin_users.router, prefix=settings.api_prefix)
    # 模型与创作主链路：前端调用 /models、/chat、/tasks 时由此统一挂载。
    app.include_router(models.router, prefix=settings.api_prefix)
    app.include_router(chat.router, prefix=settings.api_prefix)
    app.include_router(tasks.router, prefix=settings.api_prefix)
    app.include_router(uploads.router, prefix=settings.api_prefix)

    # 管理端模型维护与开放平台:此前遗漏注册,导致 /api/admin/models 与 OpenAI 兼容接口不可达。
    app.include_router(admin_models.router, prefix=settings.api_prefix)
    app.include_router(open_api.router, prefix=settings.api_prefix)



    app.include_router(admin_wallet.router, prefix=settings.api_prefix)


    return app


app = create_app()

# 测试
if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000)
