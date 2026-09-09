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
    siliconflow_api_key: str = ""
    dashscope_api_key: str = ""
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
    # CORS 白名单:逗号分隔的完整来源(如 https://portal.example.com);
    # 为空时仅允许 localhost/127.0.0.1(开发默认),生产必须显式配置
    cors_origins: str = ""

    # --- 鉴权 ---
    jwt_expire_hours: int = 24

    # --- 短信验证(阿里云 Dysmsapi;未配置时降级为日志验证码模式) ---
    aliyun_sms_access_key_id: str = ""
    aliyun_sms_access_key_secret: str = ""
    aliyun_sms_sign_name: str = ""          # 短信签名(控制台审核通过后获得)
    aliyun_sms_template_code: str = ""      # 模板 CODE(如 SMS_123456789)
    aliyun_sms_endpoint: str = "dysmsapi.aliyuncs.com"
    sms_code_expire_sec: int = 300          # 验证码有效期(秒)
    sms_code_max_attempts: int = 5          # 单条验证码最大校验失败次数
    sms_send_per_day: int = 10              # 同一手机号每日发送上限
    sms_ip_send_per_day: int = 20           # 同一 IP 每日发送上限
    # 调试模式:未配置阿里云密钥时,响应回显验证码(仅开发/演示环境开启)
    sms_debug: bool = False

    # --- 支付(支付宝沙箱;未配置时使用内置模拟收银台) ---
    alipay_app_id: str = ""
    alipay_private_key: str = ""            # 应用私钥(不带首尾行的 PEM 或纯 base64)
    alipay_public_key: str = ""             # 支付宝公钥(用于验签,非应用公钥)
    alipay_gateway: str = "https://openapi-sandbox.dl.alipaydev.com/gateway.do"
    alipay_notify_url: str = ""             # 异步通知地址(需公网可达;本地开发可用同步查单)
    alipay_return_url: str = ""             # 支付完成浏览器回跳地址(如 http://127.0.0.1:4174/pay.html)

    # --- 运营 ---
    default_register_points: int = 10       # 新用户注册赠送积分(便于新用户直接体验模型)
    # 平台盈利:按 token 计费模型在供应商成本价上加价售卖(百分数,130=加价30%);
    # 模型行 token_markup_pct 非空时优先生效
    token_markup_pct: int = 130

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

    @property
    def upload_path(self) -> Path:
        """上传与生成产物的绝对目录,不随 uvicorn 启动目录变化。"""
        path = Path(self.upload_dir)
        return path if path.is_absolute() else BASE_DIR / path


@lru_cache
def get_settings() -> Settings:
    return Settings()  # 缺失必填变量时 pydantic 会抛出含变量名的 ValidationError
