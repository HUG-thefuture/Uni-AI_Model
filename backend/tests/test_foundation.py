"""地基自测:JWT 依赖与扣费事务(冻结/结算/释放,失败不扣费)。"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.core.deps import get_current_user
from app.core.response import APIError
from app.core.security import create_access_token
from app.models.support import User, Wallet
from app.services import billing


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _user(db, role="user", status=1):
    u = User(username="u1", password_hash="x", role=role, status=status)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _auth_header(db, user):
    token = create_access_token(user.id, user.role)
    return {"Authorization": f"Bearer {token}"}, token


def test_jwt_user_lookup_and_disabled_invalid(db, monkeypatch):
    user = _user(db)
    header, _ = _auth_header(db, user)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    from app.core.response import register_exception_handlers
    register_exception_handlers(app)  # APIError(401) → 统一响应

    def _override_db():
        yield db

    from app.core import deps as deps_mod

    app.dependency_overrides[deps_mod.get_db] = _override_db

    @app.get("/me")
    def me(u: User = __import__("fastapi").Depends(get_current_user)):
        return {"id": u.id}

    client = TestClient(app, raise_server_exceptions=False)
    # 正常用户可鉴权
    assert client.get("/me", headers=header).status_code == 200
    # 禁用立即失效
    user.status = 0
    db.commit()
    assert client.get("/me", headers=header).status_code == 401
    # 伪造 token
    assert client.get("/me", headers={"Authorization": "Bearer fake"}).status_code == 401


def test_billing_freeze_settle_refund(db):
    user = _user(db)
    db.add(Wallet(user_id=user.id, balance=10))
    db.commit()
    billing.freeze(db, user.id, 6)
    db.commit()
    assert db.get(Wallet, user.id).balance == 4
    billing.settle(db, user.id, 6, task_id=1, model_id=1)
    db.commit()
    assert db.get(Wallet, user.id).total_consumed == 6
    billing.refund(db, user.id, 6)  # 失败释放
    db.commit()
    assert db.get(Wallet, user.id).balance == 10


def test_billing_insufficient_raises_409(db):
    user = _user(db)
    db.add(Wallet(user_id=user.id, balance=1))
    db.commit()
    with pytest.raises(APIError) as e:
        billing.freeze(db, user.id, 5)
    assert e.value.status_code == 409
