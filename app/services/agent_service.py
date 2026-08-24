"""Agent 的增删改查业务逻辑。

【大白话】这是"助手的管家"。接口层（api/）只负责收请求、返回结果，
真正干活（校验、存取数据库、算返回值）都在这里。分层的好处：
同一个逻辑能被多个接口复用，也方便单独写测试。

设计说明：所有对外函数返回**响应模型 AgentOut**（而非数据库对象），
这样依赖关联关系（比如 knowledge_base_ids）在数据库会话还开着时就算好、
变成普通数据返回，避免"会话关了再去查询报错"的坑。
"""

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Agent, AgentKbBinding, KnowledgeBase
from app.schemas.agent import AgentCreate, AgentOut, AgentUpdate


# ---------- 内部工具 ----------

def to_out(agent: Agent) -> AgentOut:
    """把数据库对象转成响应模型 AgentOut。

    【为什么不能直接靠 ORM 自动转】因为 knowledge_base_ids 在表里不存在，
    它要从"关联的绑定记录"里现算出来——所以要手动拼这一个字段。
    ORM 对象 agent.bindings 是它的绑定列表，我们取出每个绑定的 knowledge_base_id 拼成列表。
    """
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
        knowledge_base_ids=[b.knowledge_base_id for b in agent.bindings],  # 从绑定关系算出
        status=agent.status,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


def _get_or_404(db: Session, agent_id: int) -> Agent:
    """按 id 找助手；找不到就抛 404 错误（FastAPI 会转成 HTTP 404 响应）。

    【为什么单独抽个函数】好几个接口都要"先找助手，找不到就报404"，
    抽出来免得每处重写一遍相同的逻辑。
    """
    agent = db.get(Agent, agent_id)  # db.get(类, id)：按主键快速取一行；没有就返回 None
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent {agent_id} 不存在")
    return agent


def _unique_name_guard(db: Session, name: str, exclude_id: int | None = None) -> None:
    """校验名称唯一，重名抛 409。

    exclude_id：修改时排除"自己"——改自己的名字不算重名（排掉自己那条再查）。
    【为什么要应用层再查一次】数据库虽也有 UNIQUE 约束兜底，但应用层先查能给
    用户一个友好的中文提示（409 冲突），而不是粗暴的数据库报错。
    """
    stmt = select(Agent).where(Agent.name == name)
    if exclude_id is not None:
        stmt = stmt.where(Agent.id != exclude_id)
    if db.scalar(stmt) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"名称 '{name}' 已被使用")


def _validate_kb_ids(db: Session, knowledge_base_ids: list[int]) -> None:
    """绑定前校验知识库真实存在（应用层保证完整性，物理外键见 decisions.md）。

    【为什么】模块 2 之后，绑定"一个不存在的知识库 id"没意义。
    虽然没加数据库外键，但我们在这一层拦截：传进来的 id 在知识库表里查不到就报 400。
    """
    if not knowledge_base_ids:
        return
    existed = set(
        db.scalars(select(KnowledgeBase.id).where(KnowledgeBase.id.in_(knowledge_base_ids))).all()
    )
    missing = sorted(set(knowledge_base_ids) - existed)
    if missing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"要绑定的知识库不存在：{missing}")


def _replace_bindings(db: Session, agent: Agent, knowledge_base_ids: list[int]) -> None:
    """重建绑定关系：先清空再插入（全量替换）。

    【设计取舍】不是"增量加/增量删"，而是"整个换掉"。
    因为你前端传来的是"最终想绑定的完整列表"，全量替换最简单、可预测——
    传 [] 就解绑所有，传 [1,2] 就只绑这俩。
    """
    agent.bindings = [AgentKbBinding(knowledge_base_id=kid) for kid in knowledge_base_ids]
    db.flush()  # 先把这个改动"提交到本次事务"，但不 commit——等真正成功再最终保存


# ---------- 对外接口 ----------

def create_agent(db: Session, payload: AgentCreate) -> AgentOut:
    """创建助手。步骤：查重 → 新建 → 建绑定 → 保存并返回。"""
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
    db.add(agent)          # 告诉会话"待会儿插一行"
    db.flush()             # 先落 id（此时 agent.id 有值了），下面建绑定要用它当外键
    _validate_kb_ids(db, payload.knowledge_base_ids)  # 校验知识库存在
    _replace_bindings(db, agent, payload.knowledge_base_ids)
    db.commit()            # 真正写进数据库（失败则整笔回滚，不留半截数据）
    db.refresh(agent)      # 重新从数据库读最新值（拿到 created_at 等数据库自动填的字段）
    return to_out(agent)


def list_agents(
    db: Session,
    page: int = 1,
    size: int = 20,
    name: str | None = None,
) -> tuple[list[AgentOut], int]:
    """查询助手列表（带分页 + 可选按名称模糊过滤）。返回 (当前页数据, 总数)。

    【分页原理】count 查总数，_select 只取这一页：跳过头 (page-1)*size 条，再取 size 条。
    """
    stmt = select(Agent)          # 主查询
    count_stmt = select(func.count()).select_from(Agent)  # 数量查询（count(*)）
    if name:
        like = f"%{name}%"        # SQL 的 LIKE：%xx% 表示"包含 xx"
        stmt = stmt.where(Agent.name.like(like))
        count_stmt = count_stmt.where(Agent.name.like(like))

    total = db.scalar(count_stmt) or 0
    items = db.scalars(stmt.order_by(Agent.id).offset((page - 1) * size).limit(size)).all()
    return [to_out(a) for a in items], total


def get_agent(db: Session, agent_id: int) -> AgentOut:
    """查单个助手详情（找不到返回 404）。"""
    return to_out(_get_or_404(db, agent_id))


def update_agent(db: Session, agent_id: int, payload: AgentUpdate) -> AgentOut:
    """修改助手（只改传了的字段）。实现"部分更新"的两个关键：exclude_unset + None 判断。"""
    agent = _get_or_404(db, agent_id)

    # model_dump(exclude_unset=True)：只保留"请求体里真出现过的字段"。
    # 这样前端没传的字段就不会出现在 changes 里，天然实现"只改传了的"。
    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes:
        _unique_name_guard(db, payload.name, exclude_id=agent_id)  # 改名也要查重（排除自己）

    for field, value in changes.items():
        if field == "knowledge_base_ids":
            continue  # 绑定关系单独处理（见下面），不是普通字段
        setattr(agent, field, value)  # setattr 动态改属性：agent.name = value 这类

    # 重新绑定：没传就不动；传了（哪怕传空列表）就全量替换
    if "knowledge_base_ids" in changes:
        _validate_kb_ids(db, payload.knowledge_base_ids)
        _replace_bindings(db, agent, payload.knowledge_base_ids)

    db.commit()
    db.refresh(agent)
    return to_out(agent)


def delete_agent(db: Session, agent_id: int) -> None:
    """删除助手（级联删绑定）。返回 None，接口层返回 204 无内容。"""
    agent = _get_or_404(db, agent_id)
    db.delete(agent)  # cascade="all, delete-orphan" 让它顺带把绑定记录也删了
    db.commit()