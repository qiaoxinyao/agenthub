"""Agent 管理 CRUD 的接口测试。

依赖：本机 MySQL 运行中（root/123456，库 agenthub 已建）。
每个测试用唯一名称，测完必删，避免污染。
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    # 用 with 触发 lifespan（init_db 建表）；裸调用不会执行启动事件
    with TestClient(app) as c:
        yield c


def _uniq(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def test_create_and_get_agent(client):
    name = _uniq("测试Agent")
    resp = client.post("/api/agents", json={"name": name, "description": "测试用", "temperature": 0.5})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    agent_id = body["id"]
    try:
        assert body["name"] == name
        assert body["temperature"] == 0.5
        assert body["use_rag"] is False
        assert body["tools"] == []
        # 详情接口
        resp2 = client.get(f"/api/agents/{agent_id}")
        assert resp2.status_code == 200
        assert resp2.json()["name"] == name
    finally:
        client.delete(f"/api/agents/{agent_id}")


def test_list_agents_with_pagination(client):
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
    name = _uniq("改")
    r = client.post("/api/agents", json={"name": name, "max_tokens": 512, "use_rag": False})
    agent_id = r.json()["id"]
    try:
        # 只改部分字段：max_tokens + 绑定两个知识库 id
        resp = client.put(f"/api/agents/{agent_id}", json={"max_tokens": 2048, "knowledge_base_ids": [1, 2]})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["max_tokens"] == 2048
        assert body["knowledge_base_ids"] == [1, 2]
        assert body["name"] == name          # 没传的字段保持不变
        assert body["use_rag"] is False       # 没传的字段保持不变
    finally:
        client.delete(f"/api/agents/{agent_id}")


def test_duplicate_name_conflict(client):
    name = _uniq("重名")
    r1 = client.post("/api/agents", json={"name": name})
    agent_id = r1.json()["id"]
    try:
        r2 = client.post("/api/agents", json={"name": name})
        assert r2.status_code == 409          # 重名必须被拒
    finally:
        client.delete(f"/api/agents/{agent_id}")


def test_not_found_404(client):
    resp = client.get("/api/agents/99999999")
    assert resp.status_code == 404


def test_delete_agent(client):
    name = _uniq("删")
    r = client.post("/api/agents", json={"name": name})
    agent_id = r.json()["id"]
    resp = client.delete(f"/api/agents/{agent_id}")
    assert resp.status_code == 204
    resp2 = client.get(f"/api/agents/{agent_id}")
    assert resp2.status_code == 404