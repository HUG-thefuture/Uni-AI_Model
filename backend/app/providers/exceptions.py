"""Provider 统一异常:所有上游(硅基流动/Ollama)异常都转换为本异常,禁止向上泄漏原始堆栈。"""


class ProviderError(Exception):
    """模型适配层统一错误。

    - code:机器可读错误码,如 provider_timeout / provider_auth / provider_rate_limit / provider_unknown
    - message_zh:可直接返回给前端的中文提示
    - raw:上游原始响应片段(仅日志使用,不返回前端)
    """

    def __init__(self, code: str, message_zh: str, raw: str | None = None):
        self.code = code
        self.message_zh = message_zh
        self.raw = raw
        super().__init__(f"[{code}] {message_zh}")
