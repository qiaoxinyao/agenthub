"""Agent 的增删改查业务逻辑。这里的函数只关心"怎么操作数据"，不关心 HTTP 细节。

设计说明：所有对外函数返回**响应模型 AgentOut**（而非 ORM 对象），
这样绑定关系等需要懒加载的字段在 session 内就完成物化，避免序列化时踩"session 已关闭"的坑。
"""

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Agent, AgentKbBinding, KnowledgeBase
from app.schemas.agent import AgentCreate, AgentOut, AgentUpdate


# ---------- 内部工具 ----------

def to_out(agent: Agent) -> AgentOut:
    """ORM 对象 → 响应模型。knowledge_base_ids 由绑定关系算出，不能靠 from_attributes 自动带出。"""
    return AgentOut(
        id=agent.id,
        name=agent.name,
        description=agent.description,
        prompt_template=agent.prompt_template,
        model_name=agent.model_name,
        temperature=agent.temperature,
        max_tokens=agent.max_tokens,
        use_rag=agent.use_rag,
        tools=agent.tools or [],
        knowledge_base_ids=[b.knowledge_base_id for b in agent.bindings],
        status=agent.status,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


def _get_or_404(db: Session, agent_id: int) -> Agent:
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent {agent_id} 不存在")
    return agent


def _unique_name_guard(db: Session, name: str, exclude_id: int | None = None) -> None:
    """校验名称唯一，重名抛 409。"""
    stmt = select(Agent).where(Agent.name == name)
    if exclude_id is not None:
        stmt = stmt.where(Agent.id != exclude_id)
    if db.scalar(stmt) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"名称 '{name}' 已被使用")


def _replace_bindings(db: Session, agent: Agent, knowledge_base_ids: list[int]) -> None:
    """重建绑定关系：先清空再插入（全量替换，简单可控）。"""
    agent.bindings = [AgentKbBinding(knowledge_base_id=kid) for kid in knowledge_base_ids]
    db.flush()


def _validate_kb_ids(db: Session, knowledge_base_ids: list[int]) -> None:
    """绑定前校验知识库真实存在（应用层保证完整性，物理外键见 decisions.md）。"""
    if not knowledge_base_ids:
        return
    existed = set(
        db.scalars(select(KnowledgeBase.id).where(KnowledgeBase.id.in_(knowledge_base_ids))).all()
    )
    missing = sorted(set(knowledge_base_ids) - existed)
    if missing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"要绑定的知识库不存在：{missing}")


# ---------- 对外接口 ----------

def create_agent(db: Session, payload: AgentCreate) -> AgentOut:
    _unique_name_guard(db, payload.name)
    agent = Agent(
        name=payload.name,
        description=payload.description,
        prompt_template=payload.prompt_template,
        model_name=payload.model_name,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        use_rag=payload.use_rag,
        tools=payload.tools,
        status=payload.status,
    )
    db.add(agent)
    db.flush()  # 先落 id，绑定时才能挂上 agent_id
    _validate_kb_ids(db, payload.knowledge_base_ids)
    _replace_bindings(db, agent, payload.knowledge_base_ids)
    db.commit()
    db.refresh(agent)
    return to_out(agent)


def list_agents(
    db: Session,
    page: int = 1,
    size: int = 20,
    name: str | None = None,
) -> tuple[list[AgentOut], int]:
    """返回 (当前页数据, 总数)。分页从 1 开始。"""
    stmt = select(Agent)
    count_stmt = select(func.count()).select_from(Agent)
    if name:
        like = f"%{name}%"
        stmt = stmt.where(Agent.name.like(like))
        count_stmt = count_stmt.where(Agent.name.like(like))

    total = db.scalar(count_stmt) or 0
    items = db.scalars(stmt.order_by(Agent.id).offset((page - 1) * size).limit(size)).all()
    return [to_out(a) for a in items], total


def get_agent(db: Session, agent_id: int) -> AgentOut:
    return to_out(_get_or_404(db, agent_id))


def update_agent(db: Session, agent_id: int, payload: AgentUpdate) -> AgentOut:
    agent = _get_or_404(db, agent_id)

    # 只更新传了值的字段（None = 不改）
    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes:
        _unique_name_guard(db, payload.name, exclude_id=agent_id)

    for field, value in changes.items():
        if field == "knowledge_base_ids":
            continue  # 绑定关系单独处理
        setattr(agent, field, value)

    # 重新绑定：没传就保持原样，传了（含空列表）就全量替换
    if "knowledge_base_ids" in changes:
        _validate_kb_ids(db, payload.knowledge_base_ids)
        _replace_bindings(db, agent, payload.knowledge_base_ids)

    db.commit()
    db.refresh(agent)
    return to_out(agent)


def delete_agent(db: Session, agent_id: int) -> None:
    agent = _get_or_404(db, agent_id)
    db.delete(agent)  # 级联删除绑定（cascade="all, delete-orphan"）
    db.commit()