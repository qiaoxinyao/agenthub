# API 设计文档（api.md）

> 共 14 个接口：12 个核心 + 2 个配套。全部走 RESTful，前缀 `/api`，由 FastAPI 自动生成 Swagger（`/docs`）。
> 统一约定：请求/响应均 JSON；错误统一返回 `{"detail": "错误说明"}`；分页参数统一 `page`（默认1）`size`（默认20）。

## 一、Agent 管理（模块 1）

### 1. 创建 Agent
- `POST /api/agents`
- 请求体：`{ "name", "description", "prompt_template", "model_name", "temperature", "max_tokens", "use_rag", "tools", "knowledge_base_ids" }`
- 响应：`{ "id", ...完整字段 }`（201）
- 用途：新建一个 Agent 及其初始配置。

### 2. 查询 Agent 列表
- `GET /api/agents?page=1&size=20&name=`
- 响应：`{ "items": [...], "total": n }`
- 用途：后台管理页列出所有 Agent；支持按名称模糊过滤。

### 3. 查询单个 Agent 详情
- `GET /api/agents/{id}`
- 响应：Agent 完整配置 + 绑定的知识库 id 列表 + 绑定的工具名
- 用途：编辑页回显 / 对话前校验配置。

### 4. 修改 Agent
- `PUT /api/agents/{id}`
- 请求体：同创建接口（缺省字段保持不变 = 部分更新）
- 响应：更新后的 Agent
- 用途：改名、改 Prompt 模板、换模型参数、调整绑定。

### 5. 删除 Agent
- `DELETE /api/agents/{id}`
- 响应：204 无内容
- 用途：下线一个 Agent，级联清理绑定关系（sessions 保留但标记失效；tables 里的 agent 外键置空或随级联删，按 database.md 决定）。

## 二、知识库与文档（模块 2）

### 6. 创建知识库
- `POST /api/knowledge-bases`
- 请求体：`{ "name", "description" }`
- 响应：知识库对象（201）
- 用途：先建库，才能在库里传文档。

### 7. 知识库列表
- `GET /api/knowledge-bases`
- 响应：`{ "items": [...], "total": n }`（含每库文档数、向量块数）
- 用途：展示有哪些知识库。

### 8. 上传文档（核心难点接口）
- `POST /api/knowledge-bases/{kb_id}/documents`
- 请求：`multipart/form-data`，字段 `file`（pdf/txt/md）
- 处理流程（后端异步）：接收文件 → 存盘 → 提取文本（PDF 用 pypdf）→ 调 Go 切分服务切块 → 逐块 Embedding → 写入 Chroma → 回填 documents 状态
- 响应：`{ "document_id", "status": "processing" }`（202 Accepted)
- 用途：把文档接入知识库，喂给 RAG 检索。

### 9. 文档列表
- `GET /api/documents?kb_id=1&page=1&size=20`
- 响应：`{ "items": [{id, filename, status, chunk_count, created_at}], "total": n }`
- 用途：查看某个知识库里有哪些文档、处理完成没有。

### 10. 删除文档
- `DELETE /api/documents/{id}`
- 响应：204
- 用途：移除文档；**同步清理 Chroma 里该文档的所有向量**（防止重复计费）。

### 11. 检索测试
- `GET /api/knowledge-bases/{kb_id}/search?query=关键词&top_k=5`
- 响应：`{ "results": [{ "chunk_text", "score", "document_id", "filename" }] }`
- 用途：开发期验证入库效果；模块 6 前是单路（向量），模块 6 后自动升级为双路融合。

## 三、对话服务（模块 3/4/5/6）

### 12. 对话（整个平台的门面接口）
- `POST /api/chat`
- 请求体：`{ "agent_id", "session_id", "message", "stream": false }`
  - `session_id`：客户端生成（推荐 UUID）；服务端用它认会话，新会话传新号即可
  - `stream`：true 时走 SSE 流式输出
- 处理流程（编排层）：取 Agent 配置 → 取历史（模块4 起）→ 需要检索则召回上下文（模块2/6 起）→ 需要工具则 Function Calling（模块5 起）→ 拼 Prompt → 调大模型 → 返回
- 响应：`{ "reply", "session_id", "agent_id", "usage" }` 或 SSE 流式事件
- 用途：外部系统/演示页唯一的对话入口，实现"统一 API 对外提供对话服务"。

## 四、配套接口

### 13. 会话列表
- `GET /api/sessions?agent_id=1&page=1&size=20`
- 响应：`{ "items": [{session_id, title, message_count, updated_at}], "total": n }`
- 用途：展示会话历史入口（模块 4）。

### 14. 工具调用日志
- `GET /api/tool-call-logs?session_id=xxx&page=1&size=20`
- 响应：`{ "items": [{tool_name, params, result, status, latency_ms, created_at}], "total": n }`
- 用途：审计与面试演示"工具调用留证"（模块 5）。

## 接口与模块对照表

| 模块 | 相关接口 | 验收接口 |
|------|---------|---------|
| 1 Agent 管理 | 1-5 | 1/2/4/5 |
| 2 知识库管理 | 6-11 | 8/11 |
| 3 对话服务 | 12 | 12 |
| 4 上下文管理 | 12/13 | 12（多轮验证）/13 |
| 5 工具调用 | 12/14 | 12（工具答案）/14 |
| 6 双路检索 | 11/12 | 11（融合）/12 |