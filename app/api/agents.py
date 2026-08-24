"""Agent 管理的 5 个 RESTful 接口。

【大白话】这一层很"薄"：只负责三件事——声明路由（什么方法+什么路径）、
接收请求参数、把活丢给 service 层做、把结果返回。真正的业务规则都在 service。
这样做的好处：接口层很干净，业务逻辑能单独复用和测试。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.agent import AgentCreate, AgentList, AgentOut, AgentUpdate
from app.services import agent_service

# 声明路由：所有路径以 /agents 开头，在 Swagger 里归到"Agent 管理"分组
router = APIRouter(prefix="/agents", tags=["Agent 管理"])


@router.post("", response_model=AgentOut, status_code=201, summary="创建 Agent")
def create_agent(payload: AgentCreate, db: Session = Depends(get_db)):
    """创建助手。

    payload: AgentCreate —— FastAPI 会自动校验请求体格式，不对直接 422。
    db: Depends(get_db) —— 这就是"依赖注入"：框架给每个请求发一个数据库会话，用完自动还。
    response_model + status_code：声明"成功时返回 201 + AgentOut 格式"。
    """
    return agent_service.create_agent(db, payload)


@router.get("", response_model=AgentList, summary="查询 Agent 列表")
def list_agents(
    name: str | None = Query(default=None, description="按名称模糊过滤"),
    page: int = Query(default=1, ge=1, description="页码，从 1 开始"),
    size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
):
    """查询助手列表。Query() = 查询参数（URL 里的 ?name=xx&page=1）。"""
    items, total = agent_service.list_agents(db, page=page, size=size, name=name)
    return {"items": items, "total": total}


@router.get("/{agent_id}", response_model=AgentOut, summary="查询单个 Agent 详情")
def get_agent(agent_id: int, db: Session = Depends(get_db)):
    """查询单个助手详情。{agent_id} 是路径参数（URL 里的 /agents/5）。"""
    return agent_service.get_agent(db, agent_id)


@router.put("/{agent_id}", response_model=AgentOut, summary="修改 Agent（只改传了的字段）")
def update_agent(agent_id: int, payload: AgentUpdate, db: Session = Depends(get_db)):
    """修改助手。请求体里传了哪个字段就改哪个，没传的保持不变。"""
    return agent_service.update_agent(db, agent_id, payload)


@router.delete("/{agent_id}", status_code=204, summary="删除 Agent")
def delete_agent(agent_id: int, db: Session = Depends(get_db)):
    """删除助手。204 = 删除成功且没有返回内容（HTTP 约定）。"""
    agent_service.delete_agent(db, agent_id)