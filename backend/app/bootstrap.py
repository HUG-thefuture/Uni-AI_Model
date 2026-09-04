"""应用启动与部署初始化辅助函数。

建表使用 SQLAlchemy 的幂等 create_all；模型使用仓库全部模板(基础 + 各厂商批次,
见 scripts/seed_models.py 的 TEMPLATE_PATHS)做幂等 upsert。
启动兜底只在 models 表为空时执行，避免覆盖管理员已维护的模型配置。
"""
import logging

from sqlalchemy.exc import IntegrityError

from app.core.db import SessionLocal, init_db

logger = logging.getLogger(__name__)


def initialize_database(*, seed_if_empty: bool = False) -> dict:
    """创建缺失表并按需写入模型种子，返回初始化统计。"""
    tables = init_db()
    result = {"tables": tables, "models_seeded": False, "models": 0}

    from app.models.model import Model
    from scripts.seed_models import load_template, upsert_models

    db = SessionLocal()
    try:
        should_seed = not seed_if_empty or db.query(Model).count() == 0
        if not should_seed:
            result["models"] = db.query(Model).count()
            return result

        items = load_template()
        try:
            upsert_models(db, items)
        except IntegrityError:
            # 多 worker 同时启动时，另一进程可能刚完成插入；重试即可收敛到同一结果。
            db.rollback()
            upsert_models(db, items)
        result["models_seeded"] = True
        result["models"] = len(items)
        return result
    finally:
        db.close()


def startup_initialize() -> None:
    """启动时安全补齐数据库；数据库暂不可用时不阻断健康探针。"""
    try:
        result = initialize_database(seed_if_empty=True)
        if result["models_seeded"]:
            logger.info("数据库初始化完成，写入 %s 个模型", result["models"])
    except Exception:
        logger.exception("启动数据库初始化失败；请检查 DATABASE_URL 与数据库状态")
