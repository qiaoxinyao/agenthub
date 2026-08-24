"""Agent 管理 CRUD 的接口测试。

【大白话】自动化测试 = 用代码自动"手点一遍"接口，确认行为正确。
万一以后改了代码把功能改坏了，跑一次测试就能立刻发现（这叫"防回归"）。

依赖：本机 MySQL 运行中（root/123456，库 agenthub 已建）。
每个测试用唯一名称，测完必删，避免污染数据（测试之间互不干扰）。
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    """共享的测试客户端（整个测试会话只造一次）。

    【为什么必须用 with】TestClient 用 with 包着才会触发应用的启动事件
    （lifespan —— 里面的 init_db 会建表）。裸调用不会执行启动事件，表就不会建。
    """
    with TestClient(app) as c:
        yield c


def _uniq(prefix: str) -> str:
    """拼一个唯一名字：前缀 + 8 位随机。避免多个测试用相同名字互相冲突。"""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def test_create_and_get_agent(client):
    """创建助手 → 查详情，跑通"新建→读取"链路。"""
    name = _uniq("测试Agent")
    resp = client.post("/api/agents", json={"name": name, "description": "测试用", "temperature": 0.5})
    assert resp.status_code == 201, resp.text  # 201 = 创建成功
    body = resp.json()
    agent_id = body["id"]
    try:
        assert body["name"] == name
        assert body["temperature"] == 0.5      # 传进去的配置原样返回
        assert body["use_rag"] is False         # 没传的用默认值 False
        assert body["tools"] == []              # 没传的默认空列表
        # 详情接口：用刚才的 id 再查一次
        resp2 = client.get(f"/api/agents/{agent_id}")
        assert resp2.status_code == 200
        assert resp2.json()["name"] == name
    finally:
        # finally = 无论测试成功失败都清理，避免残留数据影响其它测试
        client.delete(f"/api/agents/{agent_id}")


def test_list_agents_with_pagination(client):
    """列表接口：应返回分页结构（items + total）且至少能查到刚建的。"""
    name = _uniq("列表")
    r = client.post("/api/agents", json={"name": name})
    agent_id = r.json()["id"]
    try:
        resp = client.get("/api/agents", params={"page": 1, "size": 10})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 1
        assert isinstance(body["items"], list)
    finally:
        client.delete(f"/api/agents/{agent_id}")


def test_update_agent_partial(client):
    """部分更新：只改传了的字段，没传的保持不变；同时验证绑定真实知识库。"""
    name = _uniq("改")
    r = client.post("/api/agents", json={"name": name, "max_tokens": 512, "use_rag": False})
    agent_id = r.json()["id"]
    # 先建一个真实知识库，绑定它（模块2 起绑定会校验知识库存在）
    rkb = client.post("/api/knowledge-bases", json={"name": _uniq("知识库")})
    kb_id = rkb.json()["id"]
    try:
        # 只改 max_tokens + 绑一个真实知识库
        resp = client.put(
            f"/api/agents/{agent_id}",
            json={"max_tokens": 2048, "knowledge_base_ids": [kb_id]},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["max_tokens"] == 2048        # 改的字段生效
        assert body["knowledge_base_ids"] == [kb_id]  # 绑定关系写进去了
        assert body["name"] == name              # 没传的字段保持不变
        assert body["use_rag"] is False          # 没传的字段保持不变
    finally:
        client.delete(f"/api/agents/{agent_id}")


def test_bind_missing_kb_rejected(client):
    """绑定不存在的知识库会被拒绝（400）。

    【为什么测这个】模块 2 加了"应用层校验"：绑定的库必须真实存在。
    这个测试守这条规则，防止以后有人把校验删了。
    """
    name = _uniq("坏绑定")
    r = client.post("/api/agents", json={"name": name})
    agent_id = r.json()["id"]
    try:
        resp = client.put(f"/api/agents/{agent_id}", json={"knowledge_base_ids": [999999]})
        assert resp.status_code == 400, resp.text
    finally:
        client.delete(f"/api/agents/{agent_id}")


def test_duplicate_name_conflict(client):
    """重名：创建两个同名助手，第二个应返回 409 冲突。"""
    name = _uniq("重名")
    r1 = client.post("/api/agents", json={"name": name})
    agent_id = r1.json()["id"]
    try:
        r2 = client.post("/api/agents", json={"name": name})
        assert r2.status_code == 409          # 409 = 冲突（名称唯一）
    finally:
        client.delete(f"/api/agents/{agent_id}")


def test_not_found_404(client):
    """"查一个不存在的 id 应返回 404（资源不存在）。"""
    resp = client.get("/api/agents/99999999")
    assert resp.status_code == 404


def test_delete_agent(client):
    """删除：先 204 删成功，再查它应 404（说明真删掉了）。"""
    name = _uniq("删")
    r = client.post("/api/agents", json={"name": name})
    agent_id = r.json()["id"]
    resp = client.delete(f"/api/agents/{agent_id}")
    assert resp.status_code == 204             # 204 = 删除成功、无返回体
    resp2 = client.get(f"/api/agents/{agent_id}")
    assert resp2.status_code == 404            # 已不存在