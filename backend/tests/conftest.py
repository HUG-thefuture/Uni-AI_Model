"""pytest 共享配置:在导入 app.* 之前注入必需环境变量(测试用 sqlite/占位密钥)。"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_ai_portal.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("SILICONFLOW_API_KEY", "")
