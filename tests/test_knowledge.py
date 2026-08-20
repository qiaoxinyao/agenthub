"""知识库管理的接口测试：KB CRUD / 上传(TXT+PDF) / 检索 / 删除。

依赖：本机 MySQL + Chroma（./data/chroma）+ Go 切分服务(8080) + 百炼 API（向量化）。
每个测试创建独有数据，测完删除（向量同步清理）。
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
    with TestClient(app) as c:  # with 触发 lifespan（init_db 建表）
        yield c


def _uniq(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _make_pdf(text: str) -> bytes:
    """生成一个含中文/英文文本的最小 PDF（pypdf 可读回）。"""
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


SAMPLE_TXT = """AgentHub 是一个面向企业内部的 Agent 应用管理平台。
它支持创建多个 Agent，为每个 Agent 配置专属的知识库和工具。
平台通过统一的 RESTful API 对外提供对话服务。
内置 RAG 检索、工具调用与任务编排能力。""" * 10


def test_create_and_list_kb(client):
    name = _uniq("测试知识库")
    r = client.post("/api/knowledge-bases", json={"name": name, "description": "自动化测试"})
    assert r.status_code == 201, r.text
    kb_id = r.json()["id"]
    try:
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
    kb_id = client.post("/api/knowledge-bases", json={"name": _uniq("文本文档库")}).json()["id"]
    try:
        # 上传 TXT
        r = client.post(
            f"/api/knowledge-bases/{kb_id}/documents",
            files={"file": ("README.txt", SAMPLE_TXT.encode(), "text/plain")},
        )
        assert r.status_code == 201, r.text
        doc = r.json()
        doc_id = doc["id"]
        assert doc["status"] == "ready", doc
        assert doc["chunk_count"] > 0, doc

        # 文档列表能看到它
        lst = client.get("/api/documents", params={"kb_id": kb_id}).json()
        assert any(d["id"] == doc_id for d in lst["items"])

        # 检索测试：用文档里的关键词，应命中相关片段（字面+语义结合）
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

        # 删除文档 → 向量同步清理；再次删除同一文档应 404（说明台账已删）
        rd = client.delete(f"/api/documents/{doc_id}")
        assert rd.status_code == 204
        assert client.delete(f"/api/documents/{doc_id}").status_code == 404
    finally:
        client.delete(f"/api/documents?kb_id={kb_id}")


def test_upload_pdf_search(client):
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
        assert doc["status"] == "ready", doc
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
    kb_id = client.post("/api/knowledge-bases", json={"name": _uniq("类型校验")}).json()["id"]
    try:
        r = client.post(
            f"/api/knowledge-bases/{kb_id}/documents",
            files={"file": ("evil.exe", b"MZ...", "application/octet-stream")},
        )
        assert r.status_code == 400, r.text
    finally:
        client.delete(f"/api/documents?kb_id={kb_id}")