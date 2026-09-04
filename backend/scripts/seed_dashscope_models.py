"""阿里云百炼 DashScope 模型种子脚本:从 docs/model-config-dashscope.json 幂等写入 models 表。

用法(在 backend/ 目录下执行):

    python scripts/seed_dashscope_models.py

- 复用 app/model_seed.py 的 upsert 逻辑(vendor=dashscope 的 5 个模型);
- 幂等:按 model_code+provider_type 判重,可重复执行;
- 一步到位(建表 + 全部模板,含本文件)请直接: python -m app.init_db
- config_json 只存非敏感参数,密钥一律走环境变量 DASHSCOPE_API_KEY。
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.model_seed import (  # noqa: E402 统一实现在 app/model_seed.py
    TEMPLATE_DIR,
    load_template as _load_template_file,
    seed_one,
)

TEMPLATE_PATH = TEMPLATE_DIR / "model-config-dashscope.json"

__all__ = ["TEMPLATE_PATH", "load_template", "main"]


def load_template(path: Path | None = None) -> list[dict]:
    """兼容旧签名:缺省读 docs/model-config-dashscope.json。"""
    return _load_template_file(path or TEMPLATE_PATH)


def main() -> int:
    """建表(幂等)→ 读 dashscope 模板 → 逐条 upsert → 输出结果。"""
    try:
        result = seed_one(TEMPLATE_PATH)
    except Exception as exc:  # noqa: BLE001 环境变量缺失/模板缺失给出明确提示
        print(f"[seed] 初始化失败: {exc}", file=sys.stderr)
        print("[seed] 请在 backend/ 目录下执行,并确认 .env 已配置 DATABASE_URL / SECRET_KEY",
              file=sys.stderr)
        return 1
    print(f"[seed] 完成: 共 {result['total']} 个, 新增 {result['created']} 个, 更新 {result['updated']} 个")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
