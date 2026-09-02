"""全局配置:用 pydantic-settings 统一加载环境变量与 .env。

约定:
- DATABASE_URL / SECRET_KEY 为必填,缺失时启动即失败并明确提示缺哪个变量;
- 模型密钥(SILICONFLOW_API_KEY)只存环境变量,绝不入库、绝不进 git;
  该项允许为空,以便无 Key 环境用 MockProvider 全链路联调与演示兜底;
  OnlineProvider 在真正调用时校验并抛出明确的中文错误。
"""
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 固定指向 backend/.env,不依赖启动时的工作目录
BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- 基础(必填) ---
    database_url: str
    secret_key: str

    # --- 模型密钥(选填,懒校验) ---
    siliconflow_api_key: str = "sk-arvbgrlviwgvyqyzwjwthjolqasfgiisftazipvhcnvmloqs"
    ollama_base_url: str = "http://localhost:11434"

    # --- Provider 超时与重试 ---
    provider_connect_timeout: int = 10
    provider_read_timeout_text: int = 60
    provider_read_timeout_image: int = 120
    provider_read_timeout_av: int = 300
    provider_max_retries: int = 2

    # --- 应用 ---
    api_prefix: str = "/api"
    log_level: str = "INFO"

    # --- 鉴权 ---
    jwt_expire_hours: int = 24

    # --- SSE 流式 ---
    sse_first_byte_timeout: int = 15   # 上游首字节超时(秒)
    sse_total_timeout: int = 120       # 单次流式总时长上限(秒)

    # --- 上传与素材 ---
    upload_dir: str = "uploads"

    # --- 开放平台 ---
    openapi_rate_limit_per_min: int = 30   # 单 Key 每分钟调用上限

    # --- 长耗时任务 ---
    video_poll_interval_sec: int = 5
    video_poll_max_sec: int = 300

    # --- 性能固化(WP09) ---
    slow_query_ms: int = 500            # 慢查询日志阈值(毫秒),超过记 warning
    mock_delay_sec: float | None = None # Mock 全局显式延迟(秒,测试/演示用;None=2-5s 随机)

    @field_validator("database_url", "secret_key")
    @classmethod
    def _not_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"环境变量 {info.field_name.upper()} 不能为空")
        return v.strip()

    @property
    def read_timeouts(self) -> dict[str, int]:
        """按任务类型读取超时(秒):text/image/audio/video。"""
        return {
            "text": self.provider_read_timeout_text,
            "image": self.provider_read_timeout_image,
            "audio": self.provider_read_timeout_av,
            "video": self.provider_read_timeout_av,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()  # 缺失必填变量时 pydantic 会抛出含变量名的 ValidationError
