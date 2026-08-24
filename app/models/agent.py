"""Agent 相关数据模型：agents 表 + agent_kb_bindings 绑定表。

【大白话】"数据模型" = 用 Python 类描述一张数据库表长什么样。
你创建一个 Agent，本质就是在 agents 表里插一行数据。

这里有两个模型：
- Agent：一张"AI 助手"的配置卡（叫什么、用什么提示词、模型参数……）
- AgentKbBinding：记录"哪个助手绑了哪个知识库"（一个助手可绑多个库，一个库可被多个助手绑 = 多对多）

注：agent_kb_bindings.knowledge_base_id 暂不设数据库外键——知识库表在模块 2 才建，
届时用"应用层校验"（绑定前查知识库存不存在）保证数据正确，见 decisions.md。
"""

from datetime import datetime

# mapped_column 描述"这一列的长相"，各种类型（String/Text/...）决定存什么格式
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Agent(Base):
    """AI 助手配置表。

    【大白话】每行 = 一个 AI 助手。字段就是它的各项配置：
    - 叫什么名、负责什么（name / description）
    - 用什么样的"岗位说明书"回答（prompt_template）
    - 用哪个大模型、回答多"放飞自我"（model_name / temperature / max_tokens）
    - 要不要查资料再回答（use_rag）、能调哪些工具（tools）、停用（status）
    """

    __tablename__ = "agents"  # 数据库里表名（和类名一致，但显式写上更清楚）

    # 主键 id：自增整数，每行一个独一无二的编号。BIGINT 表示"很大范围内的整数"。
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # 名称；unique 表"不能重名"
    description: Mapped[str] = mapped_column(String(255), default="")          # 一句话描述
    prompt_template: Mapped[str] = mapped_column(Text, default="")              # 提示词模板（Text=长文本）
    model_name: Mapped[str] = mapped_column(String(64), default="qwen3.7-plus")  # 默认模型（用户账号有免费额度）
    temperature: Mapped[float] = mapped_column(Float, default=0.7)  # 温度 0~2：越低回答越"规矩"
    max_tokens: Mapped[int] = mapped_column(Integer, default=1024)  # 最多回答多少 token（token≈字数）
    use_rag: Mapped[bool] = mapped_column(Boolean, default=False)   # 是否检索知识库（True 才"先查再答"）
    tools: Mapped[list] = mapped_column(JSON, default=list)         # 绑定的工具名列表，如 ["kb_search", "get_time"]
    status: Mapped[int] = mapped_column(Integer, default=1)         # 1=启用 0=停用
    # server_default=func.now()：由数据库自动填当前时间（比在 Python 里填更可靠/统一）
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # onupdate=func.now()：每次更新这行时，数据库自动刷新"更新时间"
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # 与绑定表的一对多关系。`cascade="all, delete-orphan"`：
    # 【为什么重要】删掉一个 Agent 时，它绑定的所有"绑定记录"自动跟着删，防止数据库里残留孤儿数据。
    bindings: Mapped[list["AgentKbBinding"]] = relationship(
        back_populates="agent", cascade="all, delete-orphan"
    )


class AgentKbBinding(Base):
    """助手↔知识库 的绑定关系表（多对多的"中间表"）。

    【为什么需要它】一个助手能绑多个知识库、一个知识库能被多个助手绑（多对多）。
    多对多关系在关系型数据库里必须拆成一张"中间表"来记：一行 = "某助手绑了某库"。
    """

    __tablename__ = "agent_kb_bindings"
    # 联合唯一约束：同一个(agent_id, knowledge_base_id)只能出现一次，防止重复绑定
    __table_args__ = (UniqueConstraint("agent_id", "knowledge_base_id", name="uq_agent_kb"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # ForeignKey("agents.id")：这一列的值，必须是 agents 表里某个存在的 id（数据库保证"引用不能悬空"）
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), nullable=False)
    knowledge_base_id: Mapped[int] = mapped_column(Integer, nullable=False)  # 模块2 补 FK（见此文件顶部说明）
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 反向关系：用 Agent 对象能直接 .bindings 拿到它绑的所有行；Back-populates 让两边互相能找
    agent: Mapped[Agent] = relationship(back_populates="bindings")