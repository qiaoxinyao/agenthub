"""上下文管理的测试：多轮对话记忆 + 滑窗 + 会话列表。

依赖：本机 MySQL + Redis(6379) + 百炼 API。
核心验证：同一 session_id 连续两轮，第二轮能"记得"第一轮的内容（模块 4 的验收标准）。
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


def test_multi_turn_memory(client):
    """验收测试：第一轮告诉它一个名字，第二轮问名字——必须答得上来。"""
    name = _uniq("记忆助手")
    r = client.post("/api/agents", json={
        "name": name,
        "prompt_template": "你是记忆测试助手，用户告诉你什么你就记住，问什么答什么。",
    })
    agent_id = r.json()["id"]
    # 同一会话号：两轮共享历史
    sid = f"s-{uuid.uuid4().hex[:12]}"
    try:
        # 第一轮：告诉它一个"暗号"
        r1 = client.post("/api/chat", json={
            "agent_id": agent_id, "session_id": sid,
            "message": "我的暗号是菠萝披萨1234，请记住",
        })
        assert r1.status_code == 200, r1.text

        # 第二轮（新请求、同一个会话）：问暗号
        r2 = client.post("/api/chat", json={
            "agent_id": agent_id, "session_id": sid,
            "message": "我的暗号是什么？只回答暗号本身。",
        })
        assert r2.status_code == 200, r2.text
        reply = r2.json()["reply"]
        assert "菠萝披萨1234" in reply, f"第二轮应记得第一轮的暗号，实际回答: {reply}"
    finally:
        client.delete(f"/api/agents/{agent_id}")


def test_different_session_no_memory_leak(client):
    """不同会话之间不能串台：A 会话说的暗号，B 会话不该知道。"""
    name = _uniq("隔离助手")
    r = client.post("/api/agents", json={"name": name})
    agent_id = r.json()["id"]
    try:
        sid_a = f"a-{uuid.uuid4().hex[:8]}"
        sid_b = f"b-{uuid.uuid4().hex[:8]}"
        # A 会话存暗号
        ra = client.post("/api/chat", json={
            "agent_id": agent_id, "session_id": sid_a,
            "message": "我的暗号是西瓜汽水5678，请记住",
        })
        assert ra.status_code == 200

        # B 会话问暗号——应该不知道（这正是我们要的行为）
        rb = client.post("/api/chat", json={
            "agent_id": agent_id, "session_id": sid_b,
            "message": "我的暗号是什么？如果不知道就回答'不知道'三个字。",
        })
        assert rb.status_code == 200
        assert "西瓜汽水5678" not in rb.json()["reply"], "B 会话不应知道 A 会话的暗号"
    finally:
        client.delete(f"/api/agents/{agent_id}")


def test_sessions_list(client):
    """会话列表接口：对话过后，列表里能看到这场会话且计数正确。"""
    name = _uniq("台账助手")
    r = client.post("/api/agents", json={"name": name})
    agent_id = r.json()["id"]
    sid = f"l-{uuid.uuid4().hex[:10]}"
    try:
        # 聊一轮（1 问 1 答 = 2 条消息）
        rc = client.post("/api/chat", json={
            "agent_id": agent_id, "session_id": sid, "message": "你好呀",
        })
        assert rc.status_code == 200

        resp = client.get("/api/sessions", params={"size": 100}).json()
        mine = [s for s in resp["items"] if s["session_id"] == sid]
        assert len(mine) == 1, f"会话列表应包含刚聊的会话: {sid}"
        assert mine[0]["message_count"] == 2   # 用户1条 + 助手1条
        assert len(mine[0]["title"]) > 0       # 首轮消息自动成了标题
    finally:
        client.delete(f"/api/agents/{agent_id}")


def test_sliding_window_unit():
    """单元级验证滑窗：塞很多轮进 Redis，get_history 只返回最近几轮。

    【为什么单独测】滑窗是省钱省 token 的关键逻辑，用纯 Redis 操作测，
    不走大模型（快、不花钱）。
    """
    from app.services import context_service

    sid = f"w-{uuid.uuid4().hex[:8]}"
    try:
        # 塞 20 条消息（10 轮）
        for i in range(20):
            role = "user" if i % 2 == 0 else "assistant"
            context_service.append_message(sid, role, f"消息{i}")
        # 取最近 3 轮 = 6 条
        history = context_service.get_history(sid, max_rounds=3)
        assert len(history) == 6
        # 最后一条应该是第 19 条消息（最新），第一条是第 14 条
        assert history[-1]["content"] == "消息19"
        assert history[0]["content"] == "消息14"
    finally:
        context_service.clear_history(sid)
