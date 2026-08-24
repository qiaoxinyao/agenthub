"""大模型抽象层：全项目**唯一**直接接触"大模型 / 向量模型"的地方。

【大白话】整个项目里，凡是"要调用 AI 模型"的地方，都从这个文件拿现成的函数。
好处（面试可讲）：哪天想换模型厂商（百炼 → DeepSeek → OpenAI），
只需要改 .env 里的配置，业务代码（上传、检索、对话那些）一行都不用动。
这里对外暴露两个函数：
- embed_texts / embed_one：把文字变成"向量"（模块2 用）
- （模块3 会在这里加 chat 函数：让大模型生成对话回答）
"""

# openai 官方 SDK：用 OpenAI 兼容协议去调百炼。相当于一个"既能连 OpenAI 又能连百炼"的万能电话线。
from typing import Optional

from openai import OpenAI

from app.core.config import settings

# 缓存的客户端对象。None 表示还没创建。
_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    """惰性单例：进程内只建一次客户端（复用连接，省资源）。

    【为什么叫惰性】不是一启动就建立，而是第一次真正用到它时才建立。
    这样如果某个功能没调用模型，就白白建立一个连接，省内存。
    """
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=settings.dashscope_api_key,  # 密钥从 .env 读，绝不写死在代码
            base_url=settings.llm_base_url,      # 指向百炼的兼容接口
        )
    return _client


def embed_texts(texts: list[str], model: Optional[str] = None) -> list[list[float]]:
    """批量向量化：把一批文字，每段变成一个"数字列表"（向量），按输入顺序返回。

    【大白话】把"一句话"翻译成"一串数字"。语义越相近的两句话，数字串越接近。
    返回的长相：[[0.1, 0.2, ...], [0.3, 0.4, ...], ...]（每段一个，排成一排）
    为什么批量：一次传一批给百炼，比一条条调省网络往返、省时间。
    """
    if not texts:
        return []  # 空列表直接返回，不用调模型

    # model 参数不给就用 .env 里配的 text-embedding-v4
    resp = get_client().embeddings.create(
        model=model or settings.embedding_model,
        input=texts,
    )

    # 百炼返回的结果可能顺序打乱（并行处理的），按 index 排回输入顺序，保证一一对应
    ordered = sorted(resp.data, key=lambda item: item.index)
    return [item.embedding for item in ordered]


def embed_one(text: str, model: Optional[str] = None) -> list[float]:
    """单条向量化：只给一句话，返回它的向量。底层就是调 embed_texts。"""
    return embed_texts([text], model=model)[0]


def chat(
    messages: list[dict[str, str]],
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> str:
    """让大模型生成一段回答（模块3 的核心函数）。

    参数 messages：多轮对话的消息列表，格式如 [
        {"role": "system", "content": "你是客服助手，用中文回答"},   # 系统设定（人设）
        {"role": "user",   "content": "你好"},                       # 用户的话
    ]
    role 有三种：system（人设/规则）/ user（用户）/ assistant（助手"之前说过的话"）。

    为什么传 messages 而非单个文本：大模型"没有记忆"，你给多少轮它就只看着多少轮回答。
    多轮对话其实就是"把历史都塞进 messages 再发一次"（模块 4 会做这件事）。
    """
    model = model or settings.chat_model  # 可能来自 Agent 配置（model_name）；没配就用 .env 默认
    resp = get_client().chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    # choices[0].message.content：取第一个候选回答的文本；答不出来时可能是空串，顶成 ""
    return resp.choices[0].message.content or ""