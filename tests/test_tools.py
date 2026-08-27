"""工具调用（Function Calling）测试：工具执行、调用日志落库、端到端调用。

策略：为了测试"确定性"（模型是否调用工具随 prompt 波动），每个端到端测试
都用 prompt 里写死"必须调用某工具"，让模型别无选择必须走工具链路。
这样测的是"工具加进来链路通不通"，而不是"模型想不想用工具"。

依赖：本机 MySQL + Redis + Chroma + Go chunker(8080) + 百炼 API。
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


def _agents_with_tool(client, tool_names, prompt) -> int:
    """建一个绑定了指定工具的 Agent，返回 id（供测试用，调用方负责删除）。"""
    name = _uniq("工具助手")
    r = client.post("/api/agents", json={
        "name": name,
        "prompt_template": prompt,
        "tools": tool_names,
    })
    return r.json()["id"]


def test_get_time_tool_chat(client):
    """端到端：Agent 绑 get_time，问时间 → 回答含当前日期 + 日志有 get_time 记录。"""
    prompt = (
        "你是一个时间助手。用户问你时间时，你**必须**先调用 get_time 工具"
        "获取真实时间，再回答用户。绝不要编造时间。"
    )
    aid = _agents_with_tool(client, ["get_time"], prompt)
    sid = f"t-{uuid.uuid4().hex[:10]}"
    try:
        resp = client.post("/api/chat", json={
            "agent_id": aid, "session_id": sid, "message": "现在是几点？",
        })
        assert resp.status_code == 200, resp.text
        reply = resp.json()["reply"]
        assert len(reply) > 0
        # Prompt 强制调用工具 → 回答里应带真实日期（2026）
        assert "2026" in reply, f"回答应包含检索到的当前年份: {reply}"

        # 日志里应有 get_time 且成功
        logs = client.get("/api/tool-call-logs", params={"session_id": sid}).json()
        time_logs = [l for l in logs["items"] if l["tool_name"] == "get_time"]
        assert len(time_logs) >= 1, f"应有 get_time 调用记录: {logs}"
        assert time_logs[0]["status"] == "success"
        assert time_logs[0]["result"].get("date")
    finally:
        client.delete(f"/api/agents/{aid}")


def test_kb_search_tool_in_chat(client):
    """端到端（核心验收）：Agent 绑 kb_search + 知识库 → 回答含文档内容 + 日志留证。

    【为什么是最重要测试】它验证了"Agent 真的会查资料再回答"——RAG 增强对话的完整闭环。
    """
    # 1) 建库 + 传文档
    kb_name = _uniq("资料库")
    kb_id = client.post("/api/knowledge-bases", json={"name": kb_name}).json()["id"]
    doc_text = ("苹果公司成立于1976年4月1日，创始人乔布斯和沃兹尼亚克。"
                "公司的旗舰产品包括 iPhone 智能手机。") * 6
    up = client.post(
        f"/api/knowledge-bases/{kb_id}/documents",
        files={"file": ("apple.txt", doc_text.encode(), "text/plain")},
    )
    assert up.status_code == 201
    doc_id = up.json()["id"]
    assert up.json()["status"] == "ready"

    # 2) 建 Agent：绑定该库 + 绑定 kb_search 工具 + 强制先查再答
    name = _uniq("检索助手")
    ar = client.post("/api/agents", json={
        "name": name,
        "prompt_template": (
            "你可以使用 kb_search 工具查询资料。用户提问时，"
            "你必须先调用 kb_search 确保获得相关资料，再根据资料回答。"
        ),
        "tools": ["kb_search"],
        "use_rag": True,
        "knowledge_base_ids": [kb_id],
    })
    assert ar.status_code == 201, ar.text
    aid = ar.json()["id"]
    sid = f"kb-{uuid.uuid4().hex[:10]}"
    try:
        resp = client.post("/api/chat", json={
            "agent_id": aid, "session_id": sid,
            "message": "苹果公司是哪一年成立的？",
        })
        assert resp.status_code == 200, resp.text
        reply = resp.json()["reply"]
        assert "1976" in reply, f"回答应包含检索到的成立年份: {reply}"

        # 日志里应有 kb_search 且成功
        logs = client.get("/api/tool-call-logs", params={"session_id": sid}).json()
        kb_logs = [l for l in logs["items"] if l["tool_name"] == "kb_search"]
        assert len(kb_logs) >= 1, f"应有 kb_search 调用记录: {logs}"
        assert kb_logs[0]["status"] == "success"
        assert kb_logs[0]["result"]["hits"], "kb_search 结果不应为空"
    finally:
        client.delete(f"/api/agents/{aid}")
        client.delete(f"/api/documents/{doc_id}")
        client.delete(f"/api/knowledge-bases/{kb_id}")  # 级联清，不留测试残留


def test_tool_log_listing(client):
    """工具日志列表接口结构正确（items + total + 字段齐全）。"""
    resp = client.get("/api/tool-call-logs", params={"size": 5}).json()
    assert "items" in resp and "total" in resp
    assert isinstance(resp["total"], int)
    expected = {"id", "session_id", "tool_name", "params", "result", "status", "latency_ms"}
    for item in resp["items"]:
        assert expected.issubset(item.keys()), item