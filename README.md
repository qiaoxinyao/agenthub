# AgentHub —— mini Agent 应用管理平台后端

面向企业内部的 **Agent 应用管理平台后端**（简化版 Dify）：支持创建多个 Agent、管理各自知识库、通过统一 REST API 对外提供对话服务，内置 RAG 检索、工具调用与任务编排。

> 当前进度：**模块 1（Agent 管理）已完成**，模块 2（知识库管理）进行中。README 会在「收尾」阶段按开源标准补齐（Quick Start / 架构图 / 截图）。

## 快速开始（开发期）

```bash
# 1. 创建虚拟环境并装依赖
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt

# 2. 配置环境变量（复制后填入你的百炼 API Key）
cp .env.example .env

# 3. 启动开发服务器
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

- 打开 **http://127.0.0.1:8000/ui** 使用自带控制台界面（零依赖原生 HTML+JS，随模块生长）
- 打开 http://127.0.0.1:8000/docs 查看 Swagger 接口文档

> 注意：`.env` 已被 `.gitignore` 忽略，绝不提交进仓库；真实密钥只存在于你的本机。

## 技术栈

Python 3.10+ / FastAPI / MySQL / Redis / Chroma / Elasticsearch / 阿里云百炼（OpenAI 兼容端点）/ Go（切分微服务）/ Streamlit（演示页）

## 六大功能模块（开发顺序）

1. Agent 管理 —— Agent 增删改查（名称、Prompt 模板、绑定知识库/工具、模型参数）
2. 知识库管理 —— 文档上传（PDF/TXT/MD）→ 切块 → Embedding → 向量库；列表/删除/检索测试
3. 对话服务 —— 统一 RESTful API（POST /api/chat，agent_id + session_id）
4. 上下文管理 —— 会话历史存 Redis（TTL），多轮拼接（滑窗策略）
5. 工具调用 —— 知识库检索 + 外部工具，Function Calling，调用日志落库
6. 双路检索 —— 向量库语义 + ES 关键词，融合排序

## 明确不做（后续规划）

多 Agent 协作、模型微调、权限系统、正式前端。
> 注：`/ui` 自带控制台是**开发/演示用的轻量原生界面**（零依赖、随模块生长），不属于"正式前端"；演示用 Streamlit 页在收尾阶段补齐。