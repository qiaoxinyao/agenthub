"""Agent 管理的 5 个 RESTful 接口。路由层只做"接线"，业务逻辑在 service。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.agent import AgentCreate, AgentList, AgentOut, AgentUpdate
from app.services import agent_service

router = APIRouter(prefix="/agents", tags=["Agent 管理"])


@router.post("", response_model=AgentOut, status_code=201, summary="创建 Agent")
def create_agent(payload: AgentCreate, db: Session = Depends(get_db)):
    return agent_service.create_agent(db, payload)


@router.get("", response_model=AgentList, summary="查询 Agent 列表")
def list_agents(
    name: str | None = Query(default=None, description="按名称模糊过滤"),
    page: int = Query(default=1, ge=1, description="页码，从 1 开始"),
    size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
):
    items, total = agent_service.list_agents(db, page=page, size=size, name=name)
    return {"items": items, "total": total}


@router.get("/{agent_id}", response_model=AgentOut, summary="查询单个 Agent 详情")
def get_agent(agent_id: int, db: Session = Depends(get_db)):
    return agent_service.get_agent(db, agent_id)


@router.put("/{agent_id}", response_model=AgentOut, summary="修改 Agent（只改传了的字段）")
def update_agent(agent_id: int, payload: AgentUpdate, db: Session = Depends(get_db)):
    return agent_service.update_agent(db, agent_id, payload)


@router.delete("/{agent_id}", status_code=204, summary="删除 Agent")
def delete_agent(agent_id: int, db: Session = Depends(get_db)):
    agent_service.delete_agent(db, agent_id)