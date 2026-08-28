# 架构设计文档（architecture.md）

> 对应设计文档：AgentHub 定稿 PDF（2026-08-18）。本文件是给 Claude Code 和开发者用的"第一份图纸"，后续每个模块照此施工。

## 1. 一句话架构

AgentHub 是一个前后端分离的纯后端项目：**FastAPI 提供 RESTful API，编排层串起「配置 → 历史 → 检索 → 工具 → 大模型」五步，MySQL/Redis/Chroma/ES 各司其职，百炼大模型走 OpenAI 兼容端点**。没有正式产品前端；开发/演示用**自带零依赖控制台**（`web/` → `/ui`，随模块长页签），收尾阶段再加一个 Streamlit 演示页。

## 2. 总体分层

```
┌─────────────────────────────────────────────────────────┐
│  API 层  app/api/                                       │
│  agents · knowledge · chat · sessions · tool_logs       │
└─────────────────────────┬───────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────┐
│  编排/服务层  app/services/                              │
│  chat_service（对话编排核心，调下面所有服务）              │
│  agent_service · knowledge_service · context_service    │
│  retrieval_service · tool_service                       │
└───┬───────────┬──────────────┬───────────────┬──────────┘
    ▼           ▼              ▼               ▼
  MySQL      Redis         Chroma + ES      大模型(百炼)
  业务数据    会话历史       双路检索        经 core/llm.py 封装
                              ▲
                        Go 切分微服务（chunker/，模块2 加入）
```

## 3. 数据流（一次对话全链路）

```
用户请求（Postman / 前端 / curl）
       │
       │  POST /api/chat  { agent_id, session_id, message }
       ▼
┌──────────────────────────────────────┐
│ ① API 层（FastAPI 路由）             │   校验参数、自动出 Swagger 文档
└──────────────┬───────────────────────┘
               ▼
┌──────────────────────────────────────┐
│ ② 编排层（chat 主流程调度器）         │
│  1) 取 Agent 配置／Prompt 模板       │ ─► MySQL（agents 表）
│  2) 取多轮对话历史                   │ ─► Redis（模块4 起）
│  3) 需要检索？双路检索               │ ─► Chroma(语义向量) + ES(关键词)（模块6 完整）
│  4) 需要工具？Function Calling       │ ─► 内置工具，日志写 MySQL（模块5 起）
│  5) 拼好最终 Prompt                  │
└──────────────┬───────────────────────┘
               ▼
┌──────────────────────────────────────┐
│ ③ 大模型（阿里云百炼 qwen 系列）      │   OpenAI 兼容端点，可换 DeepSeek/OpenAI
└──────────────┬───────────────────────┘
               ▼
  ④ 编排层收尾 → ⑤ API 层返回
     （默认 JSON；stream=true 时 SSE 流式）
```

## 4. 关键设计决策（）

### 4.1 模型抽象层（core/llm.py）
- 统一用 OpenAI 兼容协议调百炼，`LLM_BASE_URL` + `DASHSCOPE_API_KEY` 从 `.env` 读取。
- 效果：换模型/换厂商只改 `.env` 配置，不改业务代码 —— 这是重点设计。

### 4.2 检索可插拔（use_rag 开关）
- `agents.use_rag` 字段控制对话是否走检索。
- 模块 3 对话先"纯 LLM"跑通；知识库/双路检索完成后把开关打开，链路逐步升级，每步都可验收。

### 4.3 编排自己写，不引重框架
- 不引入 LangChain / Haystack 等。编排就是顺序代码：取配置 → 拼 Prompt → 调模型 → 返回。
- 理由：简单、可控、讲得清每一行；也是范围收敛的工程素养。

### 4.4 会话双层存储
- **MySQL sessions 表**：会话元数据（谁建的、几句了）—— 供列表展示、统计。
- **Redis**：消息本体，带 TTL —— 天然适配"多轮会话过期"，模块 4 实现。

### 4.5 双路检索（模块 6）
- 向量库（Chroma，语义） + ES（关键词）双路召回，简单融合排序。
- 模块 2 入库阶段只写 Chroma；ES 索引在模块 6 才建立并回填，避免前期白养一个不被使用的索引。

## 5. 服务依赖关系（开发期本机原生，8GB 机器）

| 服务 | 用途 | 引入时机 | 开发期形式 | 内存控制 |
|------|------|---------|-----------|---------|
| MySQL | 业务数据 | 模块 1 | 本机 MySQL 服务 | 正常配置即可 |
| Redis | 会话上下文 | 模块 4 | Windows 移植版（Memurai / redis-windows） | 极小 |
| Chroma | 向量库 | 模块 2 | pip 安装、本地目录持久化 | 进程内，极小 |
| ES | 关键词检索 | 模块 6 | 本机 ES（zip 版）| ES_JAVA_OPTS 限制堆 ≤512MB |
| Go chunker | 文本切块 | 模块 2 | go run 本机进程 | 极小 |

> Docker Compose 只用于收尾交付（clone 后一键起），开发期不常驻 Docker Desktop（8GB 内存机器扛不住常驻 JVM + 容器叠加）。

## 6. 目录结构

```
agenthub/
├── app/                    # 后端主代码
│   ├── main.py             # FastAPI 入口（含 /ui 静态托管）
│   ├── core/               # config/db/redis/llm/chunking
│   ├── models/             # SQLAlchemy 模型（6 张表）
│   ├── schemas/            # Pydantic 请求/响应
│   ├── api/                # 路由（agents/knowledge/chat/sessions/tool_logs）
│   ├── services/           # 业务逻辑
│   └── tools/              # 内置工具定义
├── web/                    # 原生 HTML+JS 控制台（/ui，零依赖，随模块生长）
│   ├── index.html
│   ├── style.css
│   └── app.js
├── chunker/                # Go 切分微服务
├── demo/                   # Streamlit 演示页（收尾）
├── docs/                   # 本文档 + database.md + api.md + decisions.md
├── tests/                  # pytest
├── scripts/                # 开发/运维脚本
├── .env / .env.example     # 密钥（忽略）/ 占位模板（入库）
└── requirements.txt / docker-compose.yml / README.md
```