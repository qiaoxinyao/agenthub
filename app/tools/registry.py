"""内置工具注册表：工具的"定义"（给大模型看的说明书）和"执行"（真正干活）都在这。

【大白话】"工具调用"（Function Calling）的原理：
- 我们把每个工具写一份"说明书"（名字、干啥的、要哪些参数）告诉大模型；
- 用户在对话里提到"现在几点"时，大模型自己判断"该调用 get_time 工具了"，
  然后返回一个"调用请求"（请用 xx 参数调用 get_time）；
- 我们后端去真的执行这个工具，把结果塞回对话里，再让大模型看着结果回答用户。

本文件 = 工具总目录。每个工具两个东西：
  1. definition：给模型看的 JSON 说明书（转成 OpenAI 协议格式）
  2. execute：真执行的函数（参数是 kwargs）

工具间互相独立，靠 ToolContext 拿到需要的"外部能力"（数据库会话、Agent 配置、向量检索）。
"""

import time  # 用于 get_time

from app.schemas.tools import ToolCallContext, ToolSpec


# ---------- 工具 1：知识库检索 ----------

def _kb_search_definition() -> dict:
    """给模型的说明书：搜知识库拿资料。"""
    return {
        "name": "kb_search",
        "description": (
            "在 Agent 绑定的知识库里做语义检索，返回最相关的几段资料原文。"
            "当用户的问题可能从已有文档中找到答案时使用（比如问产品用法、公司制度）。"
            "注意：这是'查资料'动作，回答时请引用检索到的内容。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "要检索的关键问题或关键词"},
                "top_k": {"type": "integer", "description": "返回几段，默认 3"},
            },
            "required": ["query"],
        },
    }


def _kb_search_execute(ctx: ToolCallContext, query: str, top_k: int = 3) -> dict:
    """真正执行知识库检索。

    【为什么从 Agent 的绑定库里搜】Agent 配制时通过 knowledge_base_ids 绑定了
    哪些知识库；检索只在这些库里找，不跨库。
    """
    from app.core import llm
    from app.services import vector_store

    kb_ids = ctx.agent.knowledge_base_ids
    if not kb_ids:
        return {"hits": [], "message": "该 Agent 未绑定知识库，无法检索"}

    emb = llm.embed_one(query)  # 查询也转向量，才能和文档比"像不像"
    hits = []
    for kb_id in kb_ids:
        try:
            hits.extend(vector_store.query(kb_id, emb, top_k=top_k))
        except Exception:  # 某个库没数据，跳过
            continue
    # 按相似度排序取最像的 top_k
    hits.sort(key=lambda x: x[1])
    results = [
        {"text": t[:500], "score": round(float(s), 4), "kb_id": m.get("kb_id")}
        for t, s, m in hits[:top_k]
    ]
    return {"hits": results, "kb_ids": kb_ids}


# ---------- 工具 2：当前时间 ----------

def _get_time_definition() -> dict:
    return {
        "name": "get_time",
        "description": "获取当前的日期和时间。当用户问'几点''今天几号'等问题时使用。",
        "parameters": {"type": "object", "properties": {}},  # 无参数
    }


def _get_time_execute(ctx: ToolCallContext, **kwargs) -> dict:
    from datetime import datetime
    now = datetime.now()
    # weekday：0=周一…6=周日，映射成中文全称（"星期五"比"五"更自然）
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    return {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": weekdays[now.weekday()],
    }


# ---------- 工具 3：一句名言 ----------

def _get_quote_definition() -> dict:
    return {
        "name": "get_quote",
        "description": "随机返回一句励志名言。当用户求鼓励、求名言、求打气时使用。",
        "parameters": {"type": "object", "properties": {}},
    }


def _get_quote_execute(ctx: ToolCallContext, **kwargs) -> dict:
    import random
    quotes = [
        "千里之行，始于足下。—— 老子",
        "不积跬步，无以至千里。—— 荀子",
        "学而不思则罔，思而不学则殆。—— 孔子",
        "天行健，君子以自强不息。——《周易》",
        "知之者不如好之者，好之者不如乐之者。—— 孔子",
        "宝剑锋从磨砺出，梅花香自苦寒来。——《警世贤文》",
    ]
    # 用一个随时间变化的种子，让每次调用"随机但确定"
    return {"quote": quotes[int(time.time()) % len(quotes)]}


# ---------- 注册表：名字 → (定义, 执行)。新工具在这里加一行即可。 ----------

_TOOLS: dict[str, ToolSpec] = {
    "kb_search": ToolSpec(name="kb_search", definition=_kb_search_definition(), execute=_kb_search_execute),
    "get_time": ToolSpec(name="get_time", definition=_get_time_definition(), execute=_get_time_execute),
    "get_quote": ToolSpec(name="get_quote", definition=_get_quote_definition(), execute=_get_quote_execute),
}


def get_tool(name: str) -> ToolSpec | None:
    """按名字取工具（不存在返回 None）。"""
    return _TOOLS.get(name)


def resolve_tools(tool_names: list[str]) -> list[ToolSpec]:
    """把 Agent 配置里的工具名字列表，解析成实际的工具定义列表。

    【为什么要有这层】agents.tools 存的是名字（如 ["get_time"]），
    真正执行要用到"定义 + 函数"。这里做名字→实物的映射；不认识的名字静默跳过
    （防止 Agent 配了错工具名导致对话直接崩）。
    """
    return [t for n in tool_names if (t := _TOOLS.get(n))]


def all_tool_definitions(tools: list[ToolSpec]) -> list[dict]:
    """把工具列表转成 OpenAI Function Calling 协议的 definitions 数组（调 API 用）。"""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.definition["description"],
                "parameters": t.definition["parameters"],
            },
        }
        for t in tools
    ]