# 数据库设计文档（database.md）

> 共 6 张表，全部落在 MySQL。设计原则：**表只存"元数据与配置"，大块数据（文档内容/向量/消息本体）交给专用存储（Chroma/Redis/ES）**，这样 6 张表就能装下整个平台。

## ER 关系（文字版）

```
agents ────< agent_kb_bindings >──── knowledge_bases ────< documents
   │                                              （一个知识库含多份文档）
   │
   └───< sessions                                messages 内容 → Redis
          （会话元数据）
   │
   └───< tool_call_logs
          （工具调用留证）
```

## 表 1：agents —— Agent 配置表（模块 1）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK 自增 | 主键 |
| name | VARCHAR(64) UNIQUE | 名称（唯一，改个名不能重） |
| description | VARCHAR(255) | 一句话描述 |
| prompt_template | TEXT | 提示词模板（含占位符，对话时拼装） |
| model_name | VARCHAR(64) | 模型名，默认 qwen-turbo |
| temperature | FLOAT | 温度（0-2，越低越克制） |
| max_tokens | INT | 单次回答最大 token |
| use_rag | TINYINT(1) | 是否走检索，默认 0（模块 3 先纯 LLM） |
| tools | JSON | 绑定的工具名列表，如 ["kb_search","get_time"] |
| status | TINYINT(1) | 1=启用 0=停用 |
| created_at / updated_at | DATETIME | 创建/更新时间 |

## 表 2：knowledge_bases —— 知识库表（模块 2）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK 自增 | 主键 |
| name | VARCHAR(64) | 知识库名称 |
| description | VARCHAR(255) | 描述 |
| created_at | DATETIME | 创建时间 |

## 表 3：documents —— 文档元数据表（模块 2）

> 文档正文和切块后的片段**不落 mysql**：正文只在处理时读取，切块后的片段＋向量存 Chroma（元数据带 document_id + chunk_index）。此表只做"有哪些文档、处理到哪了"的台账。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK 自增 | 主键 |
| kb_id | BIGINT FK→knowledge_bases.id | 属于哪个知识库 |
| filename | VARCHAR(255) | 原始文件名 |
| file_type | ENUM('pdf','txt','md') | 文件类型 |
| size_bytes | INT | 文件大小 |
| status | ENUM('pending','processing','ready','failed') | 处理状态 |
| chunk_count | INT | 切成几块（处理完回填） |
| error_msg | VARCHAR(512) | 失败原因（失败时填） |
| created_at | DATETIME | 上传时间 |

## 表 4：agent_kb_bindings —— Agent↔知识库绑定表（模块 2/3/6）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK 自增 | 主键 |
| agent_id | BIGINT FK→agents.id | Agent |
| knowledge_base_id | BIGINT FK→knowledge_bases.id | 知识库 |
| created_at | DATETIME | 绑定时间 |

> UNIQUE(agent_id, knowledge_base_id)：一个 Agent 绑同一个库只算一次。
> 工具绑定不建表：工具是代码里的固定注册表，agents.tools(JSON) 只记"绑了哪几个名"。

## 表 5：sessions —— 会话元数据表（模块 4）

> 消息内容不落 mysql，存在 Redis（TTL 自动过期）。此表只记"会话存在过"。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK 自增 | 主键 |
| session_id | VARCHAR(64) UNIQUE | 服务端生成的幂等会话号（前端传入，别用自增 id 外泄） |
| agent_id | BIGINT FK→agents.id | 这个会话属于哪个 Agent |
| title | VARCHAR(255) | 会话标题（首轮消息截断） |
| message_count | INT | 消息条数（Redis 里也有一份用于滑窗） |
| is_active | TINYINT(1) | 是否有效 |
| created_at / updated_at | DATETIME | 创建/最后活跃时间 |

## 表 6：tool_call_logs —— 工具调用日志表（模块 5）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK 自增 | 主键 |
| session_id | VARCHAR(64) | 会话号 |
| agent_id | BIGINT FK→agents.id | 哪个 Agent 调的 |
| tool_name | VARCHAR(64) | 工具名 |
| params | JSON | 调用入参 |
| result | JSON | 调用结果 |
| status | VARCHAR(16) | success / error |
| latency_ms | INT | 耗时（毫秒） |
| created_at | DATETIME | 调用时间 |

## 建表建议

- 建表用 SQLAlchemy 模型 + `Base.metadata.create_all`（模块 1 引入）或手写 SQL 迁移脚本。**前期用 create_all 足够，不引入 Alembic（避免重依赖）**。
- 索引：sessions(session_id) 唯一、tool_call_logs(session_id)、documents(kb_id)。
- 删除级联：删 Agent → 清 agent_kb_bindings；删知识库 → 删旗下 documents + 同步清 Chroma 向量；删文档 → 同步清 Chroma 向量（防 embedding 重复计费）。