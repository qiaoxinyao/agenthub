"""对话服务的测试：/api/chat 能拿到大模型回答。

依赖：本机 MySQL + 百炼 API（对话会真实调用 qwen，消耗极小）。
用真实调用才能验证"全链路通"，这也是本模块的验收标准。
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def _uniq(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def test_chat_returns_reply(client):
    """核心链路：创建 Agent → 发一条消息 → 拿到非空回答。

    【为什么这是验收测试】它验证了"AI 助手真的开口说话"——
    编排 → 拼人设 → 调 qwen → 返回结果，整条对话链路通了。
    """
    name = _uniq("对话助手")
    r = client.post("/api/agents", json={
        "name": name,
        "prompt_template": "你是客服小助手，回答要简洁。请用中文。",
        "model_name": "qwen3.7-plus",
        "temperature": 0.3,
        "max_tokens": 200,
    })
    agent_id = r.json()["id"]
    try:
        resp = client.post("/api/chat", json={
            "agent_id": agent_id,
            "message": "你好，请用一句话介绍你自己",
        })
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["agent_id"] == agent_id
        assert isinstance(body["reply"], str)
        assert len(body["reply"]) > 0, "回答不应为空"
        assert "客服" in body["reply"] or "助" in body["reply"], f"回答应体现人设: {body['reply']}"
    finally:
        client.delete(f"/api/agents/{agent_id}")


def test_chat_agent_not_found(client):
    """对话一个不存在的 Agent 应返回 404。"""
    resp = client.post("/api/chat", json={"agent_id": 99999999, "message": "你好"})
    assert resp.status_code == 404


def test_chat_default_prompt_fallback(client):
    """Agent 没填提示词模板时，也能用兜底人设正常回答。"""
    name = _uniq("无模板")
    r = client.post("/api/agents", json={"name": name})  # 不填 prompt_template
    agent_id = r.json()["id"]
    try:
        resp = client.post("/api/chat", json={"agent_id": agent_id, "message": "你好"})
        assert resp.status_code == 200, resp.text
        assert len(resp.json()["reply"]) > 0
    finally:
        client.delete(f"/api/agents/{agent_id}")