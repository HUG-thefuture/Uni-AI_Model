"""模型种子模块(app/model_seed.py)回归测试。

覆盖:模板合并与去重、一步初始化 seed_all_models、幂等重跑、
seed_models.py 兼容入口(seed_demo.py 的调用方式)。
"""
import os
import tempfile
import unittest
from pathlib import Path

_DB_FILE = Path(tempfile.gettempdir()) / "uni_ai_model_test1_model_seed.db"
if _DB_FILE.exists():
    _DB_FILE.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_FILE.as_posix()}"
os.environ["SECRET_KEY"] = "test-secret-key-at-least-32-bytes-long"

from app.core.db import SessionLocal, engine  # noqa: E402
from app.model_seed import (  # noqa: E402
    DEFAULT_TEMPLATE_PATH,
    TEMPLATE_DIR,
    load_template,
    load_templates,
    seed_all_models,
    seed_one,
    upsert_models,
)
from app.models.model import Model  # noqa: E402
from sqlalchemy import func, select  # noqa: E402


def _model_count() -> int:
    with SessionLocal() as db:
        return int(db.scalar(select(func.count()).select_from(Model)) or 0)


def _codes() -> set[tuple[str, str]]:
    with SessionLocal() as db:
        return set(db.execute(select(Model.model_code, Model.provider_type)).all())


class ModelSeedTest(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        engine.dispose()
        if _DB_FILE.exists():
            _DB_FILE.unlink()

    def test_01_load_templates_merges_all(self) -> None:
        """三个模板(通用/阿里百炼/终版导出)合并去重后应为 9 个模型。"""
        items, files = load_templates()
        self.assertEqual(len(files), 3, f"应加载 3 个模板文件,实际: {files}")
        keys = [(i["model_code"], i["provider_type"]) for i in items]
        self.assertEqual(len(keys), len(set(keys)), "合并后不允许出现重复 (model_code, provider_type)")
        self.assertEqual(len(items), 16, f"合并去重后应为 16 个模型,实际 {len(items)}: {sorted(keys)}")
        dashscope_codes = {i["model_code"] for i in items if i["vendor"] == "dashscope"}
        self.assertLessEqual(
            {"qwen-plus", "qwen-turbo", "wanx2.1-t2i-turbo", "qwen-tts", "fun-asr"},
            dashscope_codes,
            "阿里百炼 5 个模型必须全部在模板中",
        )

    def test_02_seed_all_models_one_step(self) -> None:
        """一步初始化:建表 + 9 个模型全部入库。"""
        result = seed_all_models(verbose=False)
        self.assertEqual(result["total"], 16)
        self.assertEqual(result["created"], 16)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(_model_count(), 16)

    def test_03_seed_all_models_idempotent(self) -> None:
        """重复执行一步初始化:全部走更新分支,不产生重复行。"""
        result = seed_all_models(verbose=False)
        self.assertEqual((result["created"], result["updated"]), (0, 16))
        self.assertEqual(_model_count(), 16)
        self.assertEqual(len(_codes()), 16)

    def test_04_upsert_reflects_template_changes(self) -> None:
        """模板字段变更后重跑 upsert,DB 同步更新(其他人拉最新数据的核心语义)。"""
        items, _ = load_templates()
        target = next(i for i in items if i["model_code"] == "qwen-plus")
        changed = {**target, "description": "回归测试临时描述"}
        with SessionLocal() as db:
            upsert_models(db, [changed], verbose=False)
        with SessionLocal() as db:
            row = db.scalar(select(Model).where(Model.model_code == "qwen-plus"))
            self.assertIsNotNone(row)
            self.assertEqual(row.description, "回归测试临时描述")
        # 还原,避免影响其他断言
        with SessionLocal() as db:
            upsert_models(db, [target], verbose=False)

    def test_05_seed_one_and_compat_entry(self) -> None:
        """单模板补种 + seed_models.load_template() 缺省口径仍指向 template 模板。"""
        result = seed_one(DEFAULT_TEMPLATE_PATH, verbose=False)
        self.assertEqual(result["total"], 11)
        self.assertEqual(_model_count(), 16)
        from scripts.seed_models import load_template as compat_load_template

        legacy_items = compat_load_template()
        self.assertEqual(len(legacy_items), 16)
        self.assertEqual(legacy_items, load_templates()[0])


if __name__ == "__main__":
    unittest.main()
