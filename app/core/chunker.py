"""调 Go 切分微服务的 HTTP 客户端。

【大白话】切块这个"重活"是交给一个独立的 Go 小服务去做的（不是 Python 自己切）。
本文件负责：把要切的文字打包发去给 Go 服务，把切好的结果拿回来。
它相当于 Python 和 Go 之间的一座桥。为什么用 Go 做切块？见 decisions.md（Go 适合纯计算场景）。
"""

import httpx

from app.core.config import settings


def chunk_text(text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> list[str]:
    """调用 Go 服务切块，返回切好的块列表。

    【大白话】你给它一整篇文字，它返回一个列表：
      ["第一段...", "第二段...", ...]
    chunk_size：每块最多多少字（默认 500）
    chunk_overlap：相邻两块重叠多少字（默认 50）——重叠是为了防止一句话被从中间切断丢语义

    【原理】Go 服务端收到 {"text": ..., "chunk_size": ..., "chunk_overlap": ...}
    后，按"段落→行→句子"切好再装进每块 500 字里返回。
    """
    resp = httpx.post(
        f"{settings.chunker_url}/chunk",           # 地址来自 .env（默认 http://127.0.0.1:8080）
        json={"text": text, "chunk_size": chunk_size, "chunk_overlap": chunk_overlap},
        timeout=120,  # 给足超时（文本很长时切分也要时间）；超时会抛异常由上层捕获
    )
    resp.raise_for_status()  # 状态码不是 200 就抛异常（比如 Go 服务没启动），由调用方统一兜底
    return resp.json()["chunks"]  # 从 Go 返回的 JSON 里取出 chunks 列表