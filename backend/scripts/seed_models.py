"""模型种子脚本(WP03,WP08 扩展为 4 个模型):从 docs/model-config-template.json 幂等写入 models 表。

用法(在 backend/ 目录下执行):

    python scripts/seed_models.py

- 幂等:按 model_code+provider_type 判重,存在则更新字段,不存在则插入,可重复执行;
- 本脚本只补种 template 模板的 4 个模型;拉取最新全量模型数据(含阿里百炼)请直接:
    python -m app.init_db
- config_json 只存非敏感参数,密钥一律走环境变量(严禁入库);
- 执行前自动建表(幂等,已有表不受影响)。

实现统一在 app/model_seed.py,本文件仅保留兼容入口(seed_demo.py 以
``seed_models.load_template() / seed_models.upsert_models()`` 方式复用)。
"""
import sys
from pathlib import Path

# 保证可从 backend/ 目录直接执行:把 backend/ 加入 sys.path 以导入 app.*
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.model_seed import (  # noqa: E402 统一实现在 app/model_seed.py
    DEFAULT_TEMPLATE_PATH,
    SEED_FIELDS,
    load_templates,
    load_template as _load_template_file,
    seed_one,
    upsert_models,
)

# 兼容旧引用:默认 template 模板路径
TEMPLATE_PATH = DEFAULT_TEMPLATE_PATH

__all__ = ["SEED_FIELDS", "TEMPLATE_PATH", "load_template", "main", "upsert_models"]


def load_template(path: Path | None = None) -> list[dict]:
    """兼容旧签名:缺省聚合全部模板,传路径时只读指定模板。"""
    return load_templates()[0] if path is None else _load_template_file(path)


def main() -> int:
    """建表(幂等)→ 读 template 模板 → 逐条 upsert → 输出结果。"""
    try:
        result = seed_one(TEMPLATE_PATH)
    except Exception as exc:  # noqa: BLE001 环境变量缺失/模板缺失给出明确提示
        print(f"[seed] 初始化失败: {exc}", file=sys.stderr)
        print("[seed] 请在 backend/ 目录下执行,并确认 .env 已配置 DATABASE_URL / SECRET_KEY",
              file=sys.stderr)
        return 1
    print(f"[seed] 完成: 共 {result['total']} 个模型, "
          f"新增 {result['created']} 个, 更新 {result['updated']} 个")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
