"""阿里云百炼 DashScope 模型种子脚本:从 docs/model-config-dashscope.json 幂等写入 models 表。

用法(在 backend/ 目录下执行):

    python scripts/seed_dashscope_models.py

注意:``python -m app.init_all`` 已把本模板纳入聚合同步(见 seed_models.TEMPLATE_PATHS),
队友拉取代码后执行 init_all 即可拿到全部模型;本脚本保留用于只刷新 dashscope 模型的场景。

- 复用 seed_models.py 的 load_template/upsert 逻辑(vendor=dashscope 的 5 个模型);
- 幂等:按 model_code+provider_type 判重,可重复执行;
- config_json 只存非敏感参数,密钥一律走环境变量 DASHSCOPE_API_KEY。
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

TEMPLATE_PATH = BACKEND_DIR.parent / "docs" / "model-config-dashscope.json"


def main() -> int:
    try:
        from app.core.db import SessionLocal, init_db
        from scripts.seed_models import load_template, upsert_models
    except Exception as exc:  # noqa: BLE001
        print(f"[seed] 初始化失败: {exc}", file=sys.stderr)
        return 1

    init_db()
    db = SessionLocal()
    try:
        items = load_template(TEMPLATE_PATH)
        result = upsert_models(db, items)
        print(f"[seed] 完成: 共 {result['total']} 个, 新增 {result['created']} 个, 更新 {result['updated']} 个")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
