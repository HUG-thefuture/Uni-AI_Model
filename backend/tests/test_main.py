"""可运行骨架:统一返回结构 + request_id 中间件。"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_unified_response():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["message"] == "success"
    assert body["data"]["status"] == "up"
    assert body["request_id"] and len(body["request_id"]) == 36  # uuid4
    assert resp.headers["X-Request-Id"] == body["request_id"]    # 响应头贯穿


def test_404_unified_response():
    resp = client.get("/api/no-such-route")
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] != 0 and body["data"] is None
    assert body["message"]  # 中文提示
