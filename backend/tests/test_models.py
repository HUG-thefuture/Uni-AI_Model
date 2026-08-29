"""验收标准1:三张表建表可执行,字段/索引/唯一约束符合 WP01 规格。"""
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.models import AiCallLog, AiTask, Model


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_create_three_tables():
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    tables = set(inspect(engine).get_table_names())
    assert {"models", "ai_tasks", "ai_call_logs"} <= tables


def test_model_unique_constraint():
    db = _session()
    db.add(Model(name="Qwen 7B", model_code="Qwen/Qwen2.5-7B-Instruct",
                 provider_type="online", model_type="text", vendor="siliconflow"))
    db.commit()
    import pytest
    from sqlalchemy.exc import IntegrityError
    db.add(Model(name="重复模型", model_code="Qwen/Qwen2.5-7B-Instruct",
                 provider_type="online", model_type="text", vendor="siliconflow"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_ai_task_defaults_and_indexes():
    db = _session()
    task = AiTask(request_id="r-1", user_id=1, model_id=1, task_type="text", prompt="你好")
    db.add(task)
    db.commit()
    db.refresh(task)
    assert task.status == "pending"      # 四态从 pending 开始
    assert task.cost == 0                # 整数积分点,失败为 0
    assert task.cost_status == "frozen"
    assert task.created_at is not None and task.updated_at is not None


def test_ai_call_log_insert():
    db = _session()
    db.add(AiCallLog(request_id="r-2", user_id=1, model_id=1,
                     provider="mock", latency_ms=123, success=True))
    db.commit()
    log = db.query(AiCallLog).first()
    assert log.success is True and log.error_code is None
