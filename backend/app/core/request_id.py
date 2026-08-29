"""request_id 链路:每次请求生成 uuid4,写入响应头 X-Request-Id 并贯穿日志。"""
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# 贯穿整个请求生命周期的 request_id( providers/services 中直接取用 )
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def current_request_id() -> str:
    return request_id_var.get()


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-Id"] = rid
        return response
