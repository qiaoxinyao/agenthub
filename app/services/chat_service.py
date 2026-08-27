"""对话服务的编排逻辑（整个平台的"大脑"）。

【大白话】这是 Agent 真正干活的地方：收到用户一句话，按步骤拼出"给大模型的材料"，
拿到回答返回。设计成"编排骨架"，后面的能力都往这插：
  - 模块4：把 Redis 里的历史轮次加进 messages           ← 已接入
  - 模块5（本模块）：如果 Agent 配置了工具，走"工具调用循环"← 已接入
    用户问"现在几点" → 模型请求调 get_time → 我们执行 → 模型看着结果回答
"""

import json
from collections.abc import Iterator

import uuid

from sqlalchemy.orm import Session as DBSession

from app.core import llm
from app.models import Session
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import agent_service, context_service, tool_service
from app.tools.registry import all_tool_definitions, resolve_tools

# 工具调用循环的最多轮数。防止模型"反复调用工具不回答"导致死循环/烧钱。
MAX_TOOL_ROUNDS = 4


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

    步骤（模块5 版）：
      1. 拿 Agent 配置
      2. 确保会话台账存在
      3. 取 Redis 历史（滑窗）
      4. 拼 messages = [人设] + [历史] + [用户消息]
      5. 若有工具 → 走"工具调用循环"（模型可能先调工具再看结果回答）
         否则 → 直接让模型回答
      6. 本轮问答写入 Redis + 更新台账
      7. 返回
    """
    # 1) Agent 配置
    agent = agent_service.get_agent(db, payload.agent_id)

    # 2) 会话台账
    _ensure_session(db, payload, payload.message)

    # 3) 历史（滑窗）
    history = context_service.get_history(payload.session_id)

    # 4) 系统人设 + messages
    system_content = (
        agent.prompt_template.strip()
        or f"你是一个名叫「{agent.name}」的 AI 助手，请用中文自然回答。"
    )
    messages: list[dict] = [{"role": "system", "content": system_content}]
    messages.extend(history)
    messages.append({"role": "user", "content": payload.message})

    # 5) 走工具循环 or 直接回答
    reply = _chat_with_maybe_tools(db, agent, payload.session_id, messages)

    # 6) 本轮问答写入 Redis + 台账
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


def chat_stream(db: DBSession, payload: ChatRequest) -> Iterator[str]:
    """流式对话（SSE 行）。逐块把回答推给前端（打字机效果），工具阶段先推提示。

    每行形如：data: {"type":"delta","text":"..."}  或  data: {"type":"tool","tools":[...]}
    与 chat_message 同一套编排（取配置/历史/工具循环），只是"吐出去"的方式是逐块推。
    真实的回答全文在生成器结束时写进 Redis 历史 + 会话台账（先答后存，失败不留脏历史）。
    """

    def _sse(event: dict) -> str:
        return "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"

    agent = agent_service.get_agent(db, payload.agent_id)
    _ensure_session(db, payload, payload.message)
    history = context_service.get_history(payload.session_id)
    system_content = (
        agent.prompt_template.strip()
        or f"你是一个名叫「{agent.name}」的 AI 助手，请用中文自然回答。"
    )
    messages: list[dict] = [{"role": "system", "content": system_content}]
    messages.extend(history)
    messages.append({"role": "user", "content": payload.message})

    tools = resolve_tools(agent.tools or [])
    defs = all_tool_definitions(tools)
    max_rounds = MAX_TOOL_ROUNDS if tools else 1

    full_reply = ""
    exhausted = False
    try:
        for _ in range(max_rounds):
            collected: dict[int, dict] = {}  # 工具调用增量按 index 累积
            for chunk in llm.completion_stream(
                messages, tools=defs or None,
                model=agent.model_name, temperature=agent.temperature, max_tokens=agent.max_tokens,
            ):
                if chunk.get("content"):
                    full_reply += chunk["content"]
                    yield _sse({"type": "delta", "text": chunk["content"]})
                for tc in chunk.get("tool_calls") or []:
                    acc = collected.setdefault(tc["index"], {"id": "", "name": "", "arguments": ""})
                    if tc.get("id"):
                        acc["id"] = tc["id"]
                    if tc.get("name"):
                        acc["name"] += tc["name"]
                    if tc.get("arguments"):
                        acc["arguments"] += tc["arguments"]

            calls = [
                {"id": a["id"], "name": a["name"], "arguments": a["arguments"]}
                for _, a in sorted(collected.items())
            ]
            if not calls:          # 模型直接回答了，流式结束
                break

            # 有工具调用：先把 assistant(tool_calls) 回填，执行工具，下一轮继续流式拿最终回答
            messages.append({
                "role": "assistant", "content": "",
                "tool_calls": [
                    {"id": c["id"], "type": "function",
                     "function": {"name": c["name"], "arguments": c["arguments"]}} for c in calls
                ],
            })
            yield _sse({"type": "tool", "tools": [c["name"] for c in calls]})
            messages.extend(tool_service.execute_tool_calls(db, agent, payload.session_id, calls))
        else:
            exhausted = True  # 每轮都在调工具、始终没直接回答（防死循环兜底）

        if exhausted or (tools and not full_reply):
            fallback = "（工具调用次数过多，请换个问法重试。）"
            full_reply = full_reply or fallback
            yield _sse({"type": "delta", "text": full_reply})
    finally:
        # 先答后存：只有真的产生了回答才写历史与台账
        if full_reply:
            context_service.append_message(payload.session_id, "user", payload.message)
            context_service.append_message(payload.session_id, "assistant", full_reply)
            db.query(Session).filter(Session.session_id == payload.session_id).update(
                {"message_count": Session.message_count + 2}
            )
            db.commit()


def _chat_with_maybe_tools(
    db: DBSession,
    agent,
    session_id: str,
    messages: list[dict],
) -> str:
    """核心：如果有工具就走 Function Calling 循环，否则直接回答。

    循环逻辑（最多 MAX_TOOL_ROUNDS 轮）：
      1. 调模型：给 messages + 工具说明书
      2. 模型返回"工具调用请求"？→ 是真调用 → 执行 → 把结果拼回 messages → 回第1步
      3. 模型返回正常回答 → 结束
    """
    tools = resolve_tools(agent.tools or [])
    if not tools:
        # 没绑工具：老路径，直接回答（省一次判断）
        return llm.chat(
            messages,
            model=agent.model_name,
            temperature=agent.temperature,
            max_tokens=agent.max_tokens,
        )

    defs = all_tool_definitions(tools)
    for _ in range(MAX_TOOL_ROUNDS):
        content, calls = llm.chat_completion(
            messages,
            tools=defs,
            model=agent.model_name,
            temperature=agent.temperature,
            max_tokens=agent.max_tokens,
        )
        if not calls:
            return content  # 模型直接回答了

        # 模型请求调工具：把 assistant 消息(含 tool_calls)拼回对话，否则模型不知道'我自己要调'过
        messages.append({
            "role": "assistant",
            "content": content,
            "tool_calls": [
                {
                    "id": c["id"],
                    "type": "function",
                    "function": {"name": c["name"], "arguments": c["arguments"]},
                }
                for c in calls
            ],
        })
        # 执行工具 + 落库，拿到 tool 结果消息
        tool_messages = tool_service.execute_tool_calls(db, agent, session_id, calls)
        messages.extend(tool_messages)

    # 走了 MAX_TOOL_ROUNDS 还没有回答（极端情况），兜底一句，避免卡死
    return "（工具调用次数过多，请换个问法重试。）"