"""模型种子脚本:从 docs/ 下全部模型模板幂等写入 models 表(单一数据源)。

用法(在 backend/ 目录下执行):

    python scripts/seed_models.py

- 模板清单见 TEMPLATE_PATHS:基础模板 + 各厂商批次(当前含阿里百炼 DashScope);
  以后新增厂商/模型批次时,把新模板文件追加到 TEMPLATE_PATHS 即可,
  ``python -m app.init_all`` 会一步同步全部模板,队友拉代码后无需额外命令;
- 同一 (model_code, provider_type) 出现在多个模板时,后一个模板覆盖前一个;
- 按 model_code+provider_type 判重:存在则更新字段,不存在则插入,可重复执行;
- 模型数量以模板文件为准，支持线上与本地模型混合配置;
- config_json 只存非敏感参数,密钥一律走环境变量(严禁入库);
- 执行前自动建表(幂等,已有表不受影响)。
"""
import json
import sys
from pathlib import Path

# 保证可从 backend/ 目录直接执行:把 backend/ 加入 sys.path 以导入 app.*
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# 模板文件位于仓库根 docs/ 目录
DOCS_DIR = BACKEND_DIR.parent / "docs"

# 模型种子模板清单(顺序即覆盖优先级,后者覆盖前者):
# 1) model-config-template.json —— 基础模板(硅基流动线上 + Ollama 本地);
# 2) model-config-dashscope.json —— 阿里云百炼 DashScope 模型批次。
TEMPLATE_PATHS = (
    DOCS_DIR / "model-config-template.json",
    DOCS_DIR / "model-config-dashscope.json",
)

# 模板条目中需要同步到 models 表的字段(跳过 "_说明" 等下划线开头键)
SEED_FIELDS = (
    "name", "model_code", "provider_type", "model_type", "vendor", "endpoint",
    "price_per_call", "max_duration_sec", "status", "config_json",
    "description", "capability_tags",
)


def load_template(path: Path | None = None) -> list[dict]:
    """读取模板 JSON,返回模型条目列表(忽略下划线开头的说明键)。

    path 为 None 时聚合 TEMPLATE_PATHS 全部模板:同一 (model_code, provider_type)
    在多个模板中出现时后一个覆盖前一个。bootstrap/init_all/seed_demo 都走默认
    聚合口径,新增模型批次无需改动任何调用方。
    """
    paths = (path,) if path is not None else TEMPLATE_PATHS
    merged: dict[tuple[str, str], dict] = {}
    for template_path in paths:
        data = json.loads(template_path.read_text(encoding="utf-8"))
        for item in data.get("models", []):
            if isinstance(item, dict) and item.get("model_code"):
                merged[(item["model_code"], item["provider_type"])] = item
    return list(merged.values())


def upsert_models(db, items: list[dict]) -> dict:
    """幂等 upsert:按 model_code+provider_type 判重,存在更新、缺失插入。

    返回统计 {created, updated, total};调用方负责 commit(这里统一提交一次)。
    """
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
    """建表(幂等)→ 读模板 → 逐条 upsert → 输出结果。"""
    try:
        from app.core.db import Base, SessionLocal, init_db
    except Exception as exc:  # noqa: BLE001 环境变量缺失等启动失败给出明确提示
        print(f"[seed] 初始化失败: {exc}", file=sys.stderr)
        print("[seed] 请在 backend/ 目录下执行,并确认 .env 已配置 DATABASE_URL / SECRET_KEY",
              file=sys.stderr)
        return 1

    init_db()  # 幂等建表(Base.metadata.create_all,已有表不受影响)
    db = SessionLocal()
    try:
        items = load_template()
        result = upsert_models(db, items)
        print(f"[seed] 完成: 共 {result['total']} 个模型, "
              f"新增 {result['created']} 个, 更新 {result['updated']} 个")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
