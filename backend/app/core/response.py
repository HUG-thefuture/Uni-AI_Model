"""统一返回结构与异常处理(全组冻结规范)。

成功:{"code":0, "message":"success", "data":{...}, "request_id":"uuid"}
失败:对应 HTTP 状态码 + {"code":非0, "message":"中文提示", "data":null, "request_id":"uuid"}
错误码:400 参数错误 / 401 未登录 / 403 无权限 / 404 不存在 / 409 冲突 / 429 限流 / 500 异常
"""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .request_id import current_request_id

logger = logging.getLogger("app.response")


def ok(data=None, message: str = "success", http_status: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=http_status,
        content={"code": 0, "message": message, "data": data, "request_id": current_request_id()},
    )


def fail(http_status: int, message: str, code: int | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=http_status,
        content={
            "code": code if code is not None else http_status * 100,
            "message": message,
            "data": None,
            "request_id": current_request_id(),
        },
    )


class APIError(Exception):
    """业务异常:在任何路由/服务中 raise APIError(status, message) 即可返回统一结构。"""

    def __init__(self, status_code: int, message: str, code: int | None = None):
        self.status_code = status_code
        self.message = message
        self.code = code
        super().__init__(message)


_STATUS_MESSAGE = {
    400: "参数错误",
    401: "未登录或凭证失效",
    403: "无权限",
    404: "资源不存在",
    409: "资源冲突",
    429: "请求过于频繁",
    500: "服务异常",
}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def _api_error(request: Request, exc: APIError):
        return fail(exc.status_code, exc.message, exc.code)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(x) for x in first.get("loc", []) if x != "body")
        msg = f"参数错误: {loc} {first.get('msg', '')}".strip()
        return fail(400, msg)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        message = str(exc.detail) if exc.detail else _STATUS_MESSAGE.get(exc.status_code, "请求失败")
        return fail(exc.status_code, message)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        logger.exception("未处理异常: %s", exc)
        return fail(500, _STATUS_MESSAGE[500])
