# 模块 1-3 重要实现位置速查（代码地图）

> 配合 `project-map.md`（目录结构）和面试问答 PDF（话术）使用。
> 这份回答的问题是：**"XX 功能是在哪个文件里实现的？"** —— 面试演示或改代码时按图索骥。

---

## 模块 1：Agent 管理

### 核心链路：创建一个 Agent 时数据怎么流

```
web/app.js collectForm()          前端收集表单 → POST /api/agents
  ↓
app/api/agents.py @router.post    接口层收请求（参数校验交给 Pydantic）
  ↓
app/services/agent_service.py     业务层：查重名 → 建数据 → 建绑定 → 落库
  ↓
app/models/agent.py               ORM 把 Python 对象翻译成 agents 表的一行
  ↓
MySQL agents / agent_kb_bindings 表
```

### 必须记住的 5 个位置

| 功能点 | 文件:函数 | 一句话说明 |
|---|---|---|
| 5 个接口的声明 | `app/api/agents.py` | `@router.post/get/put/delete` 共 5 个路由 |
| **重名校验** | `app/services/agent_service.py` `_unique_name_guard()` | 先查再插，重名返回 409；修改时排除自己 |
| **部分更新**（只改传了的字段） | 同上 `update_agent()` | 关键一行：`model_dump(exclude_unset=True)` 只留请求里出现过的字段 |
| **绑定全量替换** | 同上 `_replace_bindings()` | 不做增量增删，整表换掉，简单可预测 |
| **绑定校验**（知识库必须存在） | 同上 `_validate_kb_ids()` | 模块 2 加的；传不存在的库 id 返回 400 |

### 数据模型速记

- `agents` 表：`app/models/agent.py` 的 `Agent` 类。注意三个字段：
  - `prompt_template`（Text）：提示词模板，模块 3 对话的人设来源
  - `use_rag`（Bool）：检索开关，模块 5/6 生效
  - `tools`（JSON）：工具名列表，模块 5 生效
- 绑定关系：同文件 `AgentKbBinding` 类。多对多中间表 + 联合唯一约束防重复绑定。

---

## 模块 2：知识库管理

### 核心链路：上传一份文档后发生什么（最重要的一条链）

```
web/app.js uploadDoc()                选文件 → FormData 发给接口
  ↓
app/api/knowledge.py upload_document()   收 multipart 文件，读成字节
  ↓
app/services/knowledge_service.py create_document()   ★ 整条流水线在这
  ├─ 1. _extract_text()              PDF 用 pypdf 提文字 / TXT·MD 直接解码
  ├─ 2. chunker.chunk_text()         app/core/chunker.py 发 HTTP 给 Go 服务切块
  ├─ 3. llm.embed_texts()            app/core/llm.py 调百炼 text-embedding-v4 向量化
  ├─ 4. vector_store.add_document_chunks()   写入 Chroma（原文+向量+元数据）
  └─ 5. 成功→status=ready+记块数 / 失败→status=failed+清残留向量
  ↓
MySQL documents 表（只记台账）+ Chroma（存正文和向量）
```

### 必须记住的 6 个位置

| 功能点 | 文件:函数 | 一句话说明 |
|---|---|---|
| 入库流水线 | `knowledge_service.py` `create_document()` | try 包住 4 步；任何一步失败统一标 failed 并回滚向量 |
| PDF 提取 | 同上 `_extract_text()` | pypdf 逐页 extract_text；BytesIO 让内存字节伪装成文件 |
| **切块算法（Go）** | `chunker/main.go` `chunkText()` | 段落→行→句子→硬切逐级降格 + 贪心装块 + 50 字滑窗重叠 |
| 调 Go 的客户端 | `app/core/chunker.py` `chunk_text()` | httpx POST {text, chunk_size, chunk_overlap} |
| 向量化入口 | `app/core/llm.py` `embed_texts()` | 批量转、按 index 排回顺序；换模型只改 .env |
| **双层检索** | `knowledge_service.py` `search_kb()` | 第 1 层字面验证（关键词不存在直接空）；第 2 层向量 + 阈值过滤 |

### 检索为什么搜"红烧肉"返回空（高频问题）

三层防线，全在 `search_kb()` 里：
1. `_extract_keywords()`：查询拆词，中英交界处切开（"RAG检索"→["RAG","检索"]）
2. `vector_store.keyword_exists()`：任一关键词在库内文本中不存在 → 直接返回 `[]`
3. `SEARCH_RELEVANCE_THRESHOLD = 0.6`：余弦距离超过 0.6 的命中也剔除

---

## 模块 3：对话服务

### 核心链路：一次对话的完整流程

```
web/app.js sendChat()               聊天框发消息 → POST /api/chat
  ↓
app/api/chat.py @router.post        接口层
  ↓
app/services/chat_service.py chat_message()   ★ 编排骨架在这
  ├─ agent_service.get_agent()      取 Agent 配置（人设/模型/温度）
  ├─ 拼 messages = [system 人设, user 消息]
  │   （注释里标了插槽：模块 4 在这插历史、模块 5/6 在这插检索结果）
  └─ llm.chat()                     core/llm.py 调百炼 qwen3.7-plus
  ↓
ChatResponse {reply, session_id, model}   返回前端渲染气泡
```

### 必须记住的 4 个位置

| 功能点 | 文件:函数 | 一句话说明 |
|---|---|---|
| 对话编排 | `chat_service.py` `chat_message()` | 三步走；插槽注释标明后续模块插入点 |
| 人设兜底 | 同上 | prompt_template 为空时用「你是名叫 xx 的助手」 |
| **模型调用收敛点** | `app/core/llm.py` `chat()` | 全项目唯一直接调对话模型的地方；messages 协议在此组装 |
| 会话号设计 | `schemas/chat.py` ChatRequest | session_id 由前端生成（UUID），模块 4 的 Redis key 就是它 |

### 一个必讲的认知（面试常问）

**大模型没有记忆**。每次对话都是独立调用，它只看得到这次传的 messages。
所以现在助手是"金鱼记忆"（问完就忘）——多轮记忆是模块 4 用 Redis 存历史、每次拼接进 messages 来实现的。

---

## 全局通用设施（三个模块共用）

| 设施 | 文件 | 说明 |
|---|---|---|
| 配置唯一入口 | `app/core/config.py` | pydantic-settings 读 .env；`settings.xxx` 全局用 |
| 数据库会话 | `app/core/db.py` `get_db()` | FastAPI 依赖注入，每请求一会话用完即还 |
| 建表 | 同上 `init_db()` | create_all 启动时建表（main.py lifespan 里调用） |
| 模型抽象层 | `app/core/llm.py` | embed_texts/embed_one/chat 三件套；换厂商只改 .env |
| 密钥安全 | `.githooks/pre-commit`、`.gitignore` | .env 双重拦截不入库 |

## 测试对应关系（改了哪就跑哪个）

| 改动范围 | 测试文件 | 数量 |
|---|---|---|
| Agent CRUD / 绑定 | `tests/test_agents.py` | 7 |
| 知识库上传/检索/删除 | `tests/test_knowledge.py` | 4 |
| 对话链路 | `tests/test_chat.py` | 3 |
| 服务起得来 | `tests/test_health.py` | 4 |
| **全量** | `python -m pytest -q` | **18** |
