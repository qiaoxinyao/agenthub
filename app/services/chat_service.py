"""对话服务的编排逻辑（整个平台的"大脑"）。

【大白话】这是 Agent 真正干活的地方：收到用户一句话，按步骤拼出"给大模型的材料"，
拿到回答返回。设计成"编排骨架"，后面模块的活都往这插：
  - 模块4（本模块）：把 Redis 里的历史轮次加进 messages ← 已接入
  - 模块5/6（检索）：把知识库检索到的片段拼进 system 提示词
"""

import uuid

from sqlalchemy.orm import Session as DBSession  # 防止和 models.session.Session 撞名

from app.core import llm
from app.models import Session
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import agent_service, context_service


def _ensure_session(db: DBSession, payload: ChatRequest, first_message: str) -> Session:
    """确保会话"户口"存在：第一次见到的 session_id 就建档，否则更新计数。

    【为什么需要】Redis 里只有消息（会过期消失），MySQL 这行是持久台账：
    会话列表页展示、统计都靠它。首条消息截前 50 字当标题。
    """
    session = db.query(Session).filter(Session.session_id == payload.session_id).first()
    if session is None:
        session = Session(
            session_id=payload.session_id,
            agent_id=payload.agent_id,
            # 标题取首轮用户消息的开头（去掉换行，列表里好看）
            title=first_message.replace("\n", " ")[:50],
            message_count=0,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
    return session


def chat_message(db: DBSession, payload: ChatRequest) -> ChatResponse:
    """处理一次对话请求。

    步骤（模块4 版）：
      1. 拿 Agent 配置（找不到会抛 404）
      2. 确保会话台账存在（MySQL sessions 表）
      3. 从 Redis 取最近几轮历史（滑窗）
      4. 拼 messages = [系统人设] + [历史...] + [本次用户消息]
      5. 调用大模型（用 Agent 配置的模型/温度/长度）
      6. 把本轮问答追加进 Redis 历史 + 更新台账计数
      7. 返回回答
    """
    # 1) 拿 Agent 配置。返回的是 AgentOut（含 prompt_template / model_name 等）
    agent = agent_service.get_agent(db, payload.agent_id)

    # 2) 会话台账（首次见到这个 session_id 就建档）
    _ensure_session(db, payload, payload.message)

    # 3) 取历史（滑窗：最多最近 5 轮）。注意此时历史里**还没有**本轮消息。
    history = context_service.get_history(payload.session_id)

    # 4) 系统人设：优先用用户填的提示词模板；没填就兜底一句（按 Agent 名字自称）
    system_content = (
        agent.prompt_template.strip()
        or f"你是一个名叫「{agent.name}」的 AI 助手，请用中文自然回答。"
    )
    messages = [{"role": "system", "content": system_content}]
    messages.extend(history)                       # 插入历史轮次（模块4 新增）
    messages.append({"role": "user", "content": payload.message})
    # 模块5/6：在这里把检索到的知识片段拼进 system_content 或单独一条 user 消息

    # 5) 调用大模型。Agent 的 model_name / temperature / max_tokens 是它的"个性配置"
    reply = llm.chat(
        messages,
        model=agent.model_name,
        temperature=agent.temperature,
        max_tokens=agent.max_tokens,
    )

    # 6) 本轮问答存入 Redis（先答完再存，失败时不留脏历史）+ 台账计数 +2
    context_service.append_message(payload.session_id, "user", payload.message)
    context_service.append_message(payload.session_id, "assistant", reply)
    db.query(Session).filter(Session.session_id == payload.session_id).update(
        {"message_count": Session.message_count + 2}
    )
    db.commit()

    return ChatResponse(
        agent_id=agent.id,
        session_id=payload.session_id,
        model=agent.model_name,
        reply=reply,
    )