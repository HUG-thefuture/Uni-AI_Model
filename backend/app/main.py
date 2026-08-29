"""FastAPI 应用入口(可运行骨架)。

- 挂 request_id 中间件与统一异常处理;
- GET /api/health:存活检查(8/29 验收门槛「项目可启动」的探针);
- 模型/任务等业务路由由成员2 后续工作包(WP02+)挂载。
"""
import logging
import sys

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.request_id import RequestIdMiddleware
from app.core.response import ok, register_exception_handlers


def create_app() -> FastAPI:
    settings = get_settings()  # 必填环境变量缺失时在此抛出,启动即失败
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] request_id=%(message)s",
        stream=sys.stdout,
    )

    app = FastAPI(title="AI 大模型门户", version="0.1.0", docs_url=f"{settings.api_prefix}/docs")
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)

    @app.get(f"{settings.api_prefix}/health")
    async def health():
        """存活探针:供 Nginx/Supervisor 与每日集成验收使用。"""
        return ok(data={"status": "up", "service": "ai-portal-backend"})

    return app


app = create_app()
