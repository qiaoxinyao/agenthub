# AgentHub

> 一个轻量级 AI Agent 应用管理平台后端 —— 简化版 Dify

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.141+-green.svg)](https://fastapi.tiangolo.com/)

---

## 📖 项目介绍

AgentHub 是一个面向企业内部的 AI Agent 应用管理平台后端，支持：

- **多 Agent 管理**：创建多个 AI 助手，每个有自己的名字、提示词、绑定的知识库和工具
- **知识库管理**：上传 PDF/TXT/MD 文档，自动切块 → 向量化 → 存入向量库
- **统一对话接口**：`POST /api/chat`，支持多轮对话、工具调用、双路检索
- **双路检索**：Elasticsearch（关键词）+ Chroma（向量）融合排序，搜得更准
- **工具调用**：Function Calling 协议，支持知识库检索、查时间、名言等工具
- **流式输出**：SSE 打字机效果，实时显示回答

**技术亮点**：
- 模型抽象层：改 `.env` 配置即可切换模型厂商（百炼/DeepSeek/OpenAI）
- 双层会话存储：Redis（消息，带 TTL）+ MySQL（台账，永久）
- 字面 + 语义双路检索：避免"矮子里拔将军"硬凑结果

---

## 🛠️ 技术栈

| 类别 | 组件 | 用途 |
|------|------|------|
| **语言** | Python 3.10+ | 主语言 |
| **Web 框架** | FastAPI 0.141+ | 异步 Web 框架，自带 Swagger |
| **ORM** | SQLAlchemy 2.0+ | 数据库操作 |
| **校验** | Pydantic 2.13+ | 请求/响应模型校验 |
| **大模型** | 阿里云百炼 | qwen 对话模型 + text-embedding 向量模型 |
| **关系数据库** | MySQL 8.0+ | 业务数据（Agent/知识库/文档/会话/日志） |
| **内存数据库** | Redis 5.0+ | 多轮会话历史（带 TTL 自动过期） |
| **向量数据库** | Chroma 0.5+ | 文档切块的向量存储（语义检索） |
| **搜索引擎** | Elasticsearch 8.11+ | 文档切块的全文索引（关键词检索） |
| **微服务** | Go 1.21+ | 纯文本切块服务（段落→行→句子→硬切） |
| **前端** | 原生 HTML+JS | /ui 控制台（零依赖） |
| **部署** | Docker Compose | 一键启动全部服务 |

---

## 🚀 快速启动

### 方式一：Docker Compose（推荐，一键启动）

```bash
# 1. 克隆项目
git clone https://github.com/qiaoxinyao/agenthub.git
cd agenthub

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入你的 DASHSCOPE_API_KEY（阿里云百炼密钥）

# 3. 一键启动
docker compose up -d

# 4. 访问 Swagger 文档
# http://localhost:8002/docs

# 5. 访问网页控制台
# http://localhost:8002/ui
```

### 方式二：本机开发（适合调试）

```bash
# 1. 克隆项目
git clone https://github.com/qiaoxinyao/agenthub.git
cd agenthub

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 MySQL/Redis/百炼等配置

# 3. 启动依赖服务
# - MySQL (本机或 Docker)
# - Redis (本机或 Docker)
# - Chroma (本机，./data/chroma)
# - Elasticsearch (限 512MB 内存)
# - Go 切分服务 (cd chunker && go run main.go)

# 4. 安装依赖
pip install -r requirements.txt

# 5. 启动后端
uvicorn app.main:app --reload --port 8002

# 6. 访问 Swagger
# http://localhost:8002/docs
```

---

## 📐 架构概览

### 整体数据流

```
┌────────────────────────────────────────────────────────────────────┐
│                         用户 / 前端 / Postman                        │
│                    (网页控制台 / API 调用 / 移动端)                    │
└────────────────────────────┬───────────────────────────────────────┘
                             │ HTTP/REST API
                             │ POST /api/chat { agent_id, session_id, message }
                             ▼
┌────────────────────────────────────────────────────────────────────┐
│  ① API 层 (app/api/)                                                │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ agents.py      │ Agent 增删改查                                  │  │
│  │ knowledge.py   │ 知识库/文档管理、检索测试                        │  │
│  │ chat.py        │ 对话接口（支持 stream=true 流式）                │  │
│  │ sessions.py    │ 会话列表                                       │  │
│  │ tool_logs.py   │ 工具调用日志                                   │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                             │ Depends(get_db)                        │
│                             ▼                                        │
└────────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────────────────┐
│  ② 编排层 (app/services/)                                           │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ chat_service.py（对话编排核心）                                 │  │
│  │   1) 取 Agent 配置 (prompt_template/model_name/temperature)     │  │
│  │   2) 取会话历史 (Redis 滑窗拼接最近 5 轮)                         │  │
│  │   3) 需要检索？→ retrieval_service (双路)                       │  │
│  │   4) 需要工具？→ tool_service (Function Calling)               │  │
│  │   5) 拼最终 Prompt → 调大模型 → 返回回答                        │  │
│  │                                                                │  │
│  │ agent_service.py     │ Agent 业务逻辑                            │  │
│  │ knowledge_service.py │ 知识库/文档业务逻辑                       │  │
│  │ context_service.py   │ Redis 会话读写 + 滑窗拼接                  │  │
│  │ retrieval_service.py │ 双路检索 (ES+Chroma 融合)                  │  │
│  │ tool_service.py      │ 工具注册表 + Function Calling 执行         │  │
│  └──────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   ③ MySQL    │    │   ④ Redis    │    │ ⑤ 大模型     │
│  业务数据    │    │  会话历史    │    │ (阿里云百炼)  │
│              │    │              │    │              │
│ agents       │    │ chat:history:│    │ qwen        │
│ knowledge_   │    │ {session_id} │    │ +           │
│ bases        │    │ [JSON list]  │    │ embedding   │
│ documents    │    │ TTL=2h       │    │             │
│ sessions     │    │              │    │             │
│ tool_call_   │    │              │    │             │
│ logs         │    │              │    │             │
│ bindings     │    │              │    │             │
└──────────────┘    └──────────────┘    └──────────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
     ┌────────────┐ ┌────────────┐ ┌────────────┐
     │ ⑥ Chroma   │ │ ⑦ ES       │ │ ⑧ chunker  │
     │ 向量库     │ │ 关键词索引  │ │ Go 切分服务  │
     │            │ │            │ │            │
     │ kb_{id}    │ │ kb_{id}_   │ │ POST       │
     │ collection │ │ chunks     │ │ /chunk     │
     │ [向量 + 文本] │ │ [BM25]     │ │ → 切块     │
     └────────────┘ └────────────┘ └────────────┘
```

### 对话接口详细流程

```
用户 POST /api/chat { agent_id: 1, session_id: "abc", message: "你好" }
│
├─► 1. API 层 (chat.py)
│   └─► 校验 payload → 转发 chat_service
│
├─► 2. 编排层 (chat_service.py)
│   │
│   ├─► 2.1 取 Agent 配置 (MySQL)
│   │   └─► SELECT * FROM agents WHERE id=1
│   │       → { prompt_template: "你是客服", model_name: "qwen", ... }
│   │
│   ├─► 2.2 取会话历史 (Redis)
│   │   └─► LRANGE chat:history:abc -10 -1
│   │       → [ {"role":"user","content":"我叫小明"},
│   │           {"role":"assistant","content":"你好小明"} ]
│   │
│   ├─► 2.3 需要检索？(agents.use_rag=true)
│   │   │
│   │   └─► retrieval_service.search(kb_id, query)
│   │       │
│   │       ├─► ES 关键词检索 → BM25 分数
│   │       │   └─► 字面验证：所有关键词都不存在 → 返回空
│   │       │
│   │       ├─► Chroma 向量检索 → 余弦相似度
│   │       │   └─► query 向量化 → 找最相似段落
│   │       │
│   │       └─► 融合排序 → 综合分 = 0.6×向量 + 0.4×ES
│   │
│   ├─► 2.4 需要工具？(agents.tools 非空)
│   │   │
│   │   └─► Function Calling 循环 (max 4 轮)
│   │       │
│   │       ├─► 调大模型 (带工具说明书)
│   │       │   └─► 模型返回 tool_calls?
│   │       │
│   │       ├─► 是 → 执行工具 → 结果写 tool_call_logs
│   │       │   └─► 拼回 messages (role=tool) → 继续循环
│   │       │
│   │       └─► 否 → 模型直接回答 → 跳出循环
│   │
│   └─► 2.5 拼最终 Prompt
│       messages = [
│         {"role": "system", "content": "你是客服"},
│         ...历史消息...,
│         {"role": "user", "content": "你好"}
│       ]
│       → 调大模型 → 得到回答
│
├─► 3. 写会话历史 (Redis)
│   └─► RPUSH chat:history:abc {"role":"user","content":"你好"}
│       RPUSH chat:history:abc {"role":"assistant","content":"你好，我是客服"}
│       EXPIRE chat:history:abc 7200
│
├─► 4. 写会话台账 (MySQL)
│   └─► INSERT INTO sessions ... ON DUPLICATE KEY UPDATE message_count=message_count+2
│
└─► 5. 返回响应
    └─► { "reply": "你好，我是客服", "session_id": "abc", "model": "qwen" }
```

---

## 📡 API 概览

### Agent 管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/agents` | 创建 Agent（名字/Prompt/模型参数/绑定知识库与工具） |
| GET | `/api/agents` | Agent 列表（支持分页） |
| GET | `/api/agents/{id}` | Agent 详情 |
| PUT | `/api/agents/{id}` | 修改 Agent（支持部分更新） |
| DELETE | `/api/agents/{id}` | 删除 Agent（级联清理绑定关系） |

### 知识库管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/knowledge-bases` | 创建知识库 |
| GET | `/api/knowledge-bases` | 知识库列表（支持分页） |
| POST | `/api/knowledge-bases/{kb_id}/documents` | 上传文档（PDF/TXT/MD，自动切块入库） |
| GET | `/api/documents` | 文档列表（支持分页，可按 kb_id 过滤） |
| DELETE | `/api/documents/{id}` | 删除文档（同步清理向量库和 ES 索引） |
| GET | `/api/knowledge-bases/{kb_id}/search` | 检索测试（双路检索：向量 + 关键词融合） |

### 对话服务

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat` | 对话接口（body：agent_id + session_id + message；stream=true 支持流式输出） |

### 配套接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/sessions` | 会话列表（可按 agent_id 过滤） |
| GET | `/api/tool-call-logs` | 工具调用日志（审计/排查用） |
| GET | `/health` | 健康检查 |
| GET | `/ui` | 网页控制台（原生 HTML+JS，零依赖） |

**完整 API 文档**：启动服务后访问 `/docs`（Swagger UI）

---

## 🔐 密钥安全

- **真实 API Key 只存在本地 `.env`**（已被 `.gitignore` 忽略，不会提交到仓库）
- 仓库内只有 `.env.example`（占位符，不含真实密钥）
- git 钩子拦截：万一误操作提交 `.env`，pre-commit/pre-push 会拦截报错
- 首次公开前建议在阿里云百炼控制台轮换 Key（作废旧 Key）

---

## 📂 项目结构

```
agenthub/
├── app/
│   ├── main.py                 # FastAPI 入口，注册路由
│   ├── core/                   # 通用能力
│   │   ├── config.py           # 统一读 .env（MySQL/Redis/百炼/Chroma/ES/Go 服务地址）
│   │   ├── db.py               # SQLAlchemy 引擎与会话
│   │   ├── redis.py            # Redis 连接
│   │   ├── llm.py              # 模型抽象层（百炼 OpenAI 兼容封装）
│   │   ├── es.py               # Elasticsearch 连接
│   │   └── chunker.py          # 调 Go 切分服务的 HTTP 客户端
│   ├── models/                 # SQLAlchemy 数据模型（6 张表）
│   ├── schemas/                # Pydantic 请求/响应模型
│   ├── api/                    # 路由层
│   │   ├── agents.py
│   │   ├── knowledge.py
│   │   ├── chat.py
│   │   ├── sessions.py
│   │   └── tool_logs.py
│   ├── services/               # 业务逻辑
│   │   ├── agent_service.py
│   │   ├── knowledge_service.py    # 上传→解析→ (调 Go) 切块→向量→入库
│   │   ├── context_service.py      # Redis 会话读写 + 滑窗拼接
│   │   ├── retrieval_service.py    # 双路检索与融合排序
│   │   ├── tool_service.py         # 工具注册表 + Function Calling 执行
│   │   └── chat_service.py         # 编排核心
│   └── tools/                  # 内置工具定义（知识库检索 + 2 个外部工具）
├── chunker/                    # Go 切分微服务
│   ├── main.go                 # HTTP POST /chunk：纯文本切块
│   └── go.mod
├── web/                        # 原生 HTML+JS 控制台（/ui）
├── tests/                      # pytest 测试
├── docs/                       # 设计文档与决策日志
├── data/                       # 本地数据（Chroma/MySQL 数据，已被 gitignore）
├── .env.example                # 环境变量模板（不含真实 Key）
├── .gitignore                  # Git 忽略规则
├── LICENSE                     # MIT 许可证
├── requirements.txt            # Python 依赖
└── README.md                   # 项目说明（本文件）
```

---

## 🧪 测试

```bash
# 运行全量测试
pytest

# 运行指定模块测试
pytest tests/test_agents.py -v
pytest tests/test_knowledge.py -v
pytest tests/test_chat.py -v
```

---

## 📝 后续规划

- [ ] 多 Agent 协作（Agent 之间可以互相调用）
- [ ] 模型微调（支持 Fine-tuning 上传）
- [ ] 权限系统（用户/角色/资源控制）
- [ ] 正式前端（Vue/React，替代当前原生 HTML 控制台）
- [ ] 中文分词器优化（ES 接入 IK 分词器）
- [ ] 向量检索归一化（BM25 和余弦分数各自归一化到 0~1 再加权）

---

## 📄 License

本项目采用 [MIT 许可证](LICENSE)。

```
Copyright (c) 2026 qiaoxinyao

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
```

---

## 👤 作者

**qiaoxinyao**

GitHub: [@qiaoxinyao](https://github.com/qiaoxinyao)

---

<div align="center">

**如果觉得有用，欢迎 ⭐ Star 支持！**

</div>
