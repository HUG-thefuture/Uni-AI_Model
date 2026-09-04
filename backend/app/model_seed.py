"""模型种子共享模块:把 docs/ 下全部模型模板幂等写入 models 表。

两条入口复用本模块:
- ``python -m app.init_db``          一步初始化:建表 + 全部模板(推荐,含阿里百炼);
- ``backend/scripts/seed_models.py`` / ``seed_dashscope_models.py``  单模板补种(兼容保留)。

规则:
- 模板放在仓库根 docs/ 下,文件名匹配 ``model-config-*.json``;
- 新增厂商模型 = 在 docs/ 新增一个模板 JSON:其他人 git pull 后执行
  ``python -m app.init_db`` 即可拿到最新模型数据,无需改代码;
- 幂等:按 (model_code, provider_type) 判重,存在更新字段、缺失插入,可重复执行;
- 多个模板出现同名模型时,文件名排序靠后的覆盖靠前的
  (终版导出 model-config-final.json 与源模板保持一致,结果不受影响);
- config_json 只存非敏感参数,密钥一律走环境变量,严禁入库。
"""
import json
from pathlib import Path

# 仓库根 docs/ 目录(本文件位于 backend/app/ 下)
TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "docs"
# 模板文件通配:新增厂商模板文件放进 docs/ 即自动纳入一步初始化
TEMPLATE_GLOB = "model-config-*.json"
# 单模板默认路径(旧 seed_models.py 兼容口径)
DEFAULT_TEMPLATE_PATH = TEMPLATE_DIR / "model-config-template.json"

# 模板条目中需要同步到 models 表的字段(跳过 "_说明" 等下划线开头键)
SEED_FIELDS = (
    "name", "model_code", "provider_type", "model_type", "vendor", "endpoint",
    "price_per_call", "max_duration_sec", "status", "config_json",
    "description", "capability_tags",
)


def load_template(path: Path) -> list[dict]:
    """读取单个模板 JSON,返回模型条目列表(忽略下划线开头的说明键)。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        item for item in data.get("models", [])
        if isinstance(item, dict) and item.get("model_code")
    ]


def load_templates(template_dir: Path | None = None) -> tuple[list[dict], list[str]]:
    """合并 docs/ 下全部 model-config-*.json,按 (model_code, provider_type) 去重。

    返回 (合并后的条目列表, 已加载文件名列表);一个模板都没有时抛 FileNotFoundError。
    """
    directory = Path(template_dir) if template_dir else TEMPLATE_DIR
    merged: dict[tuple[str, str], dict] = {}
    files: list[str] = []
    for path in sorted(directory.glob(TEMPLATE_GLOB)):
        for item in load_template(path):
            merged[(item["model_code"], item["provider_type"])] = item
        files.append(path.name)
    if not files:
        raise FileNotFoundError(f"未找到模型模板({TEMPLATE_GLOB}): {directory}")
    return list(merged.values()), files


def upsert_models(db, items: list[dict], verbose: bool = True) -> dict:
    """幂等 upsert:按 model_code+provider_type 判重,存在更新、缺失插入。

    返回统计 {created, updated, total};统一提交一次,调用方无需再 commit。
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
            if verbose:
                print(f"[seed] 新增模型: {item['name']} ({item['model_code']}/{item['provider_type']})")
        else:
            for f in SEED_FIELDS:
                setattr(existing, f, item.get(f))
            updated += 1
            if verbose:
                print(f"[seed] 更新模型: {item['name']} ({item['model_code']}/{item['provider_type']})")
    db.commit()
    return {"created": created, "updated": updated, "total": len(items)}


def _seed(items: list[dict], verbose: bool = True) -> dict:
    """建表(幂等)→ upsert 指定条目;db 导入放函数内,避免模块导入期读环境变量。"""
    from .core.db import SessionLocal, init_db

    schema_report = init_db()
    db = SessionLocal()
    try:
        result = upsert_models(db, items, verbose=verbose)
        result["schema_report"] = schema_report
        return result
    finally:
        db.close()


def seed_one(template_path: Path, verbose: bool = True) -> dict:
    """写入单个模板文件(旧 seed_models / seed_dashscope_models 入口复用)。"""
    return _seed(load_template(template_path), verbose=verbose)


def seed_all_models(template_dir: Path | None = None, verbose: bool = True) -> dict:
    """一步初始化:建表 + 合并写入 docs/ 全部模型模板(含阿里百炼 dashscope)。

    返回 {"created", "updated", "total", "files"}。
    """
    items, files = load_templates(template_dir)
    result = _seed(items, verbose=verbose)
    result["files"] = files
    return result
