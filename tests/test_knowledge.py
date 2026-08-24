"""知识库管理的接口测试：KB CRUD / 上传(TXT+PDF) / 检索 / 删除。

【大白话】这些测试会真实调用整条链路：
上传文档 → Go 切块 → 百炼转向量 → 写进向量库 → 检索。
所以它们依赖：本机 MySQL + Chroma（./data/chroma）+ Go 切分服务(8080) + 百炼 API。
每个测试创建独有数据，测完删除（向量同步清理），互不干扰。
"""

import io
import uuid

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, StreamObject

from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:  # with 触发 lifespan（init_db 建表），同 test_agents
        yield c


def _uniq(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _make_pdf(text: str) -> bytes:
    """生成一个含文本的最小 PDF（pypdf 能读回）。

    【为什么不直接放一个 PDF 文件】测试里现场生成，不依赖外部素材文件，
    而且能控制里面写了什么文字。这里用 pypdf 手工拼一个最简单的 PDF：
    - 建一页空纸
    - 往 /Contents 里写一行文字指令（BT ... Tj ET 是 PDF 的"画文字"命令）
    - 声明用内置 Helvetica 字体（标准 14 种字体不用嵌入，省事）
    """
    w = PdfWriter()
    page = w.add_blank_page(width=612, height=792)
    content = f"BT /F1 20 Tf 100 700 Td ({text}) Tj ET".encode()
    stream = StreamObject()
    stream._data = content
    page[NameObject("/Contents")] = stream
    res = DictionaryObject()
    res[NameObject("/Font")] = DictionaryObject({
        NameObject("/F1"): DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }),
    })
    page[NameObject("/Resources")] = res
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


# 测试用文本：重复 10 次，长度足够切出多个块
SAMPLE_TXT = """AgentHub 是一个面向企业内部的 Agent 应用管理平台。
它支持创建多个 Agent，为每个 Agent 配置专属的知识库和工具。
平台通过统一的 RESTful API 对外提供对话服务。
内置 RAG 检索、工具调用与任务编排能力。""" * 10


def test_create_and_list_kb(client):
    """创建知识库 → 列表里能看到它；重名应 409。"""
    name = _uniq("测试知识库")
    r = client.post("/api/knowledge-bases", json={"name": name, "description": "自动化测试"})
    assert r.status_code == 201, r.text
    kb_id = r.json()["id"]
    try:
        # size=100：一次多取点，新库排在清单里一定能被扫到（避免分页漏掉）
        lst = client.get("/api/knowledge-bases", params={"size": 100}).json()
        assert lst["total"] >= 1
        assert any(kb["id"] == kb_id for kb in lst["items"])
        # 重名冲突
        r2 = client.post("/api/knowledge-bases", json={"name": name})
        assert r2.status_code == 409
    finally:
        # 知识库没有删除接口（本次范围），仅清理库内文档
        client.delete(f"/api/documents?kb_id={kb_id}")


def test_upload_txt_search_delete(client):
    """核心链路：上传 TXT → 切块就绪 → 列表可见 → 检索命中 → 删无关词空 → 删除文档。

    【为什么这个测试最重要】它把"上传→入库→检索→删除"整条 RAG 数据链路
    从头到尾验了一遍，任何一个环节坏了都能被它抓住。
    """
    kb_id = client.post("/api/knowledge-bases", json={"name": _uniq("文本文档库")}).json()["id"]
    try:
        # 上传 TXT（files=：模拟"选了一个文件发出去"，第二个参数是文件内容字节）
        r = client.post(
            f"/api/knowledge-bases/{kb_id}/documents",
            files={"file": ("README.txt", SAMPLE_TXT.encode(), "text/plain")},
        )
        assert r.status_code == 201, r.text
        doc = r.json()
        doc_id = doc["id"]
        assert doc["status"] == "ready", doc   # 处理完成
        assert doc["chunk_count"] > 0, doc     # 切成块了

        # 文档列表能看到它
        lst = client.get("/api/documents", params={"kb_id": kb_id}).json()
        assert any(d["id"] == doc_id for d in lst["items"])

        # 检索测试：用文档里的关键词（字面+语义双层）应命中
        sr = client.get(f"/api/knowledge-bases/{kb_id}/search", params={"query": "RAG检索", "top_k": 3})
        assert sr.status_code == 200, sr.text
        hits = sr.json()["results"]
        assert len(hits) >= 1, hits
        assert hits[0]["document_id"] == doc_id
        assert "RAG" in hits[0]["chunk_text"] or "Agent" in hits[0]["chunk_text"]

        # 检索词完全不在文档里 → 应返回空结果（不再硬凑）
        sr2 = client.get(f"/api/knowledge-bases/{kb_id}/search", params={"query": "喜羊羊红烧肉", "top_k": 3})
        assert sr2.status_code == 200, sr2.text
        assert sr2.json()["results"] == [], sr2.json()

        # 删除文档 → 向量同步清理；再次删除同一文档应 404（台账已删）
        rd = client.delete(f"/api/documents/{doc_id}")
        assert rd.status_code == 204
        assert client.delete(f"/api/documents/{doc_id}").status_code == 404
    finally:
        client.delete(f"/api/documents?kb_id={kb_id}")


def test_upload_pdf_search(client):
    """PDF 上传链路：生成最小 PDF → 上传 → 提取出文字 → 检索命中。"""
    kb_id = client.post("/api/knowledge-bases", json={"name": _uniq("PDF文档库")}).json()["id"]
    try:
        pdf = _make_pdf("AgentHub is a mini agent platform for PDF testing 2026 with RAG retrieval")
        r = client.post(
            f"/api/knowledge-bases/{kb_id}/documents",
            files={"file": ("note.pdf", pdf, "application/pdf")},
        )
        assert r.status_code == 201, r.text
        doc = r.json()
        doc_id = doc["id"]
        assert doc["status"] == "ready", doc      # 说明 PDF 里文字提取成功了
        assert doc["file_type"] == "pdf"
        assert doc["chunk_count"] >= 1

        sr = client.get(f"/api/knowledge-bases/{kb_id}/search", params={"query": "PDF testing"})
        assert sr.status_code == 200
        hits = sr.json()["results"]
        assert len(hits) >= 1
        assert "PDF testing" in hits[0]["chunk_text"]

        client.delete(f"/api/documents/{doc_id}")
    finally:
        client.delete(f"/api/documents?kb_id={kb_id}")


def test_upload_reject_bad_type(client):
    """上传不支持的扩展名（.exe）应被拒（400）。

    【为什么】只有 pdf/txt/md 三类能入库，别的一律拒绝，
    防止乱七八糟的文件进来把处理流程搞崩。
    """
    kb_id = client.post("/api/knowledge-bases", json={"name": _uniq("类型校验")}).json()["id"]
    try:
        r = client.post(
            f"/api/knowledge-bases/{kb_id}/documents",
            files={"file": ("evil.exe", b"MZ...", "application/octet-stream")},
        )
        assert r.status_code == 400, r.text
    finally:
        client.delete(f"/api/documents?kb_id={kb_id}")