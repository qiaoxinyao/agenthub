"""调 Go 切分微服务的 HTTP 客户端。切块只做一件事：纯文本切块，切完发回来。"""

import httpx

from app.core.config import settings


def chunk_text(text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> list[str]:
    """调用 Go 服务切块，返回切好的块列表。"""
    resp = httpx.post(
        f"{settings.chunker_url}/chunk",
        json={"text": text, "chunk_size": chunk_size, "chunk_overlap": chunk_overlap},
        timeout=120,
    )
    resp.raise_for_status()  # Go 服务挂掉时这里会抛异常，由上层统一处理
    return resp.json()["chunks"]