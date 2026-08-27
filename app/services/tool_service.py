"""工具调用的编排逻辑：执行工具 + 调用日志落库。

【大白话】这是 Function Calling 的下半场：
大模型说"请调用 get_time 工具"（返回一个"调用请求"），这里负责真正去执行，
把执行结果变成一条"工具消息"塞回对话，让大模型看着结果回答用户。

同时把每次调用（谁调的、什么参数、什么结果、多久）写进 tool_call_logs 表，
这就是"工具调用留证"。
"""

import json
import time

from sqlalchemy.orm import Session as DBSession

from app.models import ToolCallLog
from app.schemas.agent import AgentOut
from app.schemas.tools import ToolCallContext, ToolSpec
from app.tools.registry import get_tool


def execute_tool_calls(
    db: DBSession,
    agent: AgentOut,
    session_id: str,
    calls: list[dict],
) -> list[dict]:
    """执行一批工具调用（大模型一次可能同时要调多个工具）。返回回传给模型的消息。

    calls 每个元素形如：{"id":"call_xx", "name":"get_time", "arguments":"{\"a\":1}"}
    返回的每条消息形如 OpenAI 协议里的 tool 消息：
      {"role":"tool", "tool_call_id": "...", "content": "结果JSON字符串"}

    每调用一次就写一条日志到 tool_call_logs。
    """
    tool_messages: list[dict] = []
    ctx = ToolCallContext(agent=agent)

    for call in calls:
        tool_name = call.get("name", "")
        try:
            arguments = json.loads(call.get("arguments") or "{}")  # arguments 是 JSON 字符串
        except json.JSONDecodeError:
            arguments = {}

        # 计时开始
        t0 = time.time()
        status = "success"
        try:
            tool = get_tool(tool_name)
            if tool is None:
                raise ValueError(f"工具 '{tool_name}' 不存在")
            # 执行：execute(ctx, **arguments)，用关键字参数传给工具
            result = tool.execute(ctx, **arguments)
            result = _trim(result)  # 结果过大时截断，避免撑爆上下文/日志
        except Exception as e:  # noqa: BLE001 工具出错也要记录，不让整轮对话崩掉
            status = "error"
            result = {"error": str(e)[:300]}
            tool_name = tool_name or "unknown"  # 工具不存在时也能记日志

        latency_ms = int((time.time() - t0) * 1000)

        # 落库：一次调用一行日志
        db.add(ToolCallLog(
            session_id=session_id,
            agent_id=agent.id,
            tool_name=tool_name,
            params=arguments,
            result=result,
            status=status,
            latency_ms=latency_ms,
        ))
        db.commit()

        # 拼一条 tool 消息返回给模型（协议要求 content 是字符串）
        tool_messages.append({
            "role": "tool",
            "tool_call_id": call.get("id", ""),
            "content": json.dumps(result, ensure_ascii=False),
        })

    return tool_messages


def _trim(result: dict, max_chars: int = 2000) -> dict:
    """把工具结果里过长的字符串截断，防止把日志/上下文撑爆。"""
    out = {}
    for k, v in result.items():
        if isinstance(v, str) and len(v) > max_chars:
            out[k] = v[:max_chars] + f"...(截断,共{len(v)}字)"
        elif isinstance(v, list):
            out[k] = [  # 对列表里每个 dict 也做同样的字符串截断
                _trim(item, max_chars) if isinstance(item, dict) else item
                for item in v[:50]  # 列表最多留 50 项
            ]
        else:
            out[k] = v
    return out