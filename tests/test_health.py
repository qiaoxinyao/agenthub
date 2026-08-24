"""冒烟测试：验证 FastAPI 空服务能起、关键端点可访问。

【大白话】"冒烟测试"是最基础的自动化测试——不测复杂业务，只确认
"服务能起来、关键页面能打开"。就像新机器先点火看会不会冒烟。
后续模块的测试照这个模式加。
"""

from fastapi.testclient import TestClient

from app.main import app

# TestClient：FastAPI 自带的"虚拟浏览器/客户端"。它不走网络，
# 直接在内存里模拟发请求，测完即弃。用它的好处：测试里不需要真的把服务跑起来。
client = TestClient(app)


def test_root():
    """首页接口：应返回项目信息和导航地址。"""
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["app"] == "AgentHub"
    assert body["docs"] == "/docs"


def test_health():
    """健康检查：应返回 ok。"""
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"


def test_docs():
    """Swagger 文档页：应能打开（返回的 HTML 里含 swagger）。"""
    resp = client.get("/docs")
    assert resp.status_code == 200
    assert "swagger" in resp.text.lower() or "Swagger UI" in resp.text


def test_ui_console():
    """控制台前端（静态托管）可访问。"""
    resp = client.get("/ui")
    assert resp.status_code == 200
    assert "AgentHub 控制台" in resp.text