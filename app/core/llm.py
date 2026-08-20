"""大模型抽象层：全项目**唯一**直接接触"大模型/向量模型"的地方。

设计（面试可讲）：对外只暴露 `embed` / `chat`（chat 模块3接入），
内部用 OpenAI 兼容协议调阿里云百炼。要换厂商/改模型，只动 .env 配置，业务代码零改动。
"""

from typing import Optional

from openai import OpenAI

from app.core.config import settings

_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    """惰性单例：进程内只建一次客户端（复用连接，省资源）。"""
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=settings.dashscope_api_key,
            base_url=settings.llm_base_url,
        )
    return _client


def embed_texts(texts: list[str], model: Optional[str] = None) -> list[list[float]]:
    """批量向量化。返回按输入顺序排列的向量列表。"""
    if not texts:
        return []
    resp = get_client().embeddings.create(
        model=model or settings.embedding_model,
        input=texts,
    )
    # 结果可能乱序，按 index 排回输入顺序
    ordered = sorted(resp.data, key=lambda item: item.index)
    return [item.embedding for item in ordered]


def embed_one(text: str, model: Optional[str] = None) -> list[float]:
    """单条向量化。"""
    return embed_texts([text], model=model)[0]