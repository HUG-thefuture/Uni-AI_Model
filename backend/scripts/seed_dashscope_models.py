"""阿里云百炼 DashScope 模型种子脚本:从 docs/model-config-dashscope.json 幂等写入 models 表。

用法(在 backend/ 目录下执行):

    python scripts/seed_dashscope_models.py

- 复用 seed_models.py 的 upsert 逻辑(vendor=dashscope 的 5 个模型);
- 幂等:按 model_code+provider_type 判重,可重复执行;
- config_json 只存非敏感参数,密钥一律走环境变量 DASHSCOPE_API_KEY。
"""
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

TEMPLATE_PATH = BACKEND_DIR.parent / "docs" / "model-config-dashscope.json"

SEED_FIELDS = (
    "name", "model_code", "provider_type", "model_type", "vendor", "endpoint",
    "price_per_call", "max_duration_sec", "status", "config_json",
    "description", "capability_tags",
)


def load_template(path: Path = TEMPLATE_PATH) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        item for item in data.get("models", [])
        if isinstance(item, dict) and item.get("model_code")
    ]


def upsert_models(db, items: list[dict]) -> dict:
    from app.models.model import Model

    created = updated = 0
    for item in items:
        existing = (
            db.query(Model)
            .filter(Model.model_code == item["model_code"],
                    Model.provider_type == item["provider_type"])
            .one_or_none()
        )
        if existing is None:
            db.add(Model(**{f: item.get(f) for f in SEED_FIELDS}))
            created += 1
            print(f"[seed] 新增模型: {item['name']} ({item['model_code']}/{item['provider_type']})")
        else:
            for f in SEED_FIELDS:
                setattr(existing, f, item.get(f))
            updated += 1
            print(f"[seed] 更新模型: {item['name']} ({item['model_code']}/{item['provider_type']})")
    db.commit()
    return {"created": created, "updated": updated, "total": len(items)}


def main() -> int:
    try:
        from app.core.db import SessionLocal, init_db
    except Exception as exc:  # noqa: BLE001
        print(f"[seed] 初始化失败: {exc}", file=sys.stderr)
        return 1

    init_db()
    db = SessionLocal()
    try:
        items = load_template()
        result = upsert_models(db, items)
        print(f"[seed] 完成: 共 {result['total']} 个, 新增 {result['created']} 个, 更新 {result['updated']} 个")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())