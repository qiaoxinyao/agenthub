"""冒烟测试：验证 FastAPI 空服务能起、关键端点可访问。后续模块的测试照这个模式加。"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root():
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["app"] == "AgentHub"
    assert body["docs"] == "/docs"


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"


def test_docs():
    resp = client.get("/docs")
    assert resp.status_code == 200
    assert "swagger" in resp.text.lower() or "Swagger UI" in resp.text