"""Elasticsearch 连接客户端（单例，类似 redis.py）。

【大白话】ES 是"关键词检索"专家——用户搜"红烧肉"，它能在几毫秒内找出所有含这仨字的段落。
双路检索中它负责第一路：字面验证（词不存在就直接返回空，不硬凑）。

【内存限制】开发期 ES 堆内存限 512MB（-Xms512m -Xmx512m），防止 8GB 机器被吃光。
"""

from elasticsearch import Elasticsearch

from app.core.config import settings

_es_client: Elasticsearch | None = None


def get_es() -> Elasticsearch:
    """惰性单例：第一次调用才创建连接，之后复用。

    【为什么用单例】ES 客户端创建有开销（握手/认证），全局复用一份，避免每次请求都新建。
    【探活】第一次调用时 ping 一下，连不上直接抛异常（让开发者知道 ES 没起）。
    """
    global _es_client
    if _es_client is None:
        _es_client = Elasticsearch(
            [settings.es_host],
            basic_auth=(settings.es_user, settings.es_password) if hasattr(settings, "es_user") and settings.es_user else None,
            request_timeout=10,  # 10 秒超时，防止卡死
        )
        # 探活：连不上直接抛
        if not _es_client.ping():
            raise RuntimeError(f"无法连接 Elasticsearch @ {settings.es_host}")
    return _es_client


def es_index_name(kb_id: int) -> str:
    """根据知识库 ID 生成 ES 索引名。

    格式：kb_{kb_id}_chunks
    例：kb_123_chunks → 知识库 123 的文档块索引
    """
    return f"kb_{kb_id}_chunks"
