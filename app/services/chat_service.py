"""对话服务的编排逻辑（整个平台的"大脑"）。

【大白话】这是 Agent 真正干活的地方：收到用户一句话，按步骤拼出"给大模型的材料"，
拿到回答返回。设计成"编排骨架"，后面模块的活都往这插：
  - 模块4（上下文管理）：把 Redis 里的历史轮次加进 messages
  - 模块5/6（检索）：把知识库检索到的片段拼进 system 提示词
现在模块3 阶段先"纯 LLM"跑通：取 Agent 配置 → 拼系统人设 → 调模型 → 返回。
"""

from sqlalchemy.orm import Session

from app.core import llm
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import agent_service


def chat_message(db: Session, payload: ChatRequest) -> ChatResponse:
    """处理一次对话请求。

    步骤（模块3 版）：
      1. 拿 Agent 配置（找不到会抛 404）
      2. 用它的提示词模板当"系统人设"
      3. 拼出 messages = [系统人设, 用户的话]
      4. 调用大模型（用 Agent 配置的模型/温度/长度）
      5. 返回回答 + 会话号 + 用的模型
    """
    # 1) 拿 Agent 配置。返回的是 AgentOut（含 name / prompt_template / model_name 等）
    agent = agent_service.get_agent(db, payload.agent_id)

    # 2) 系统人设：优先用用户填的提示词模板；没填就兜底一句（按 Agent 名字自称）
    system_content = agent.prompt_template.strip() or f"你是一个名叫「{agent.name}」的 AI 助手，请用中文自然回答。"
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": payload.message},
    ]
    # 模块4：在这里把会话历史（Redis）插进 messages 中间
    # 模块5/6：在这里把检索到的知识片段拼进 system_content 或单独一条 user 消息

    # 3) 调用大模型。Agent 的 model_name / temperature / max_tokens 是它的"个性配置"
    reply = llm.chat(
        messages,
        model=agent.model_name,
        temperature=agent.temperature,
        max_tokens=agent.max_tokens,
    )

    return ChatResponse(
        agent_id=agent.id,
        session_id=payload.session_id,
        model=agent.model_name,
        reply=reply,
    )