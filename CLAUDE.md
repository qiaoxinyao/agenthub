# CLAUDE.md — agenthub 项目说明书

> 这个文件是给 Claude Code 看的"项目说明书"。它放在项目根目录后，Claude Code 每次启动都会自动读取，永远知道这个项目是什么、怎么干活。
> 本文件为模板：复制到项目根目录后，根据方案审查结果微调。

## 项目是什么
- 名称：agenthub（mini Agent 应用管理平台后端）
- 一句话：面向企业内部的 Agent 平台，支持创建多个 Agent、管理各自知识库、通过统一 API 提供对话服务，内置 RAG 检索、工具调用与任务编排。
- 形态：简化版 Dify 的后端（无正式前端，仅 Streamlit 演示页）

## 技术栈（严格按项目方案，不擅自增删）
- Python 3.10+ / FastAPI（OpenAI 兼容模式接入大模型）
- 大模型：阿里云百炼（对话 qwen-turbo 调试 / qwen-plus 演示；Embedding text-embedding-v4）
- 存储：MySQL（业务数据）、Redis（会话上下文）、Chroma 向量库（语义检索）、Elasticsearch（关键词检索，双路融合）
- 部署：Docker Compose（交付物）；开发期用本机原生服务（8GB 内存机器，勿常驻 Docker Desktop）

## 六大功能模块（一次只做一个，做完一个提交一次）
1. Agent 管理：Agent 增删改查（名称、Prompt 模板、绑定知识库/工具、模型参数）
2. 知识库管理：文档上传（PDF/TXT/MD）→ 切块 → Embedding → 向量库；列表/删除/检索测试
3. 对话服务：统一 RESTful API（POST /api/chat，agent_id + session_id）
4. 上下文管理：会话历史存 Redis（TTL），多轮拼接（滑窗策略）
5. 工具调用：知识库检索 + 外部工具，Function Calling，调用日志落库
6. 双路检索：向量库语义 + ES 关键词，融合排序

## 明确不做（写进 README"后续规划"，不要实现）
多 Agent 协作、模型微调、权限系统、正式前端

## 开发规范（重要，每次对话都要遵守）
- 一次只实现一个功能，完成并测试通过后再开始下一个
- 每完成一个功能：跑通测试 → 提交一次 git（commit message 用中文，格式：`feat: 模块名 - 一句话说明`）
- 涉及设计取舍的决策，必须追加记录到 docs/decisions.md（格式：日期 + 背景 + 选择 + 原因）
- 所有解释和回复使用中文，面向"有 Python 基础但无 Agent 项目经验"的开发者的水平，讲清楚原理
- 不允许为了"炫技"引入 PDF 方案之外的依赖或框架；如确需新增，先说明理由征得同意

## 常用命令（Windows + Git Bash）
- 启动开发服务器：`uvicorn app.main:app --reload --port 8000`
- 运行测试：`pytest`（或 `python -m pytest`）
- 环境变量：复制 `.env.example` 为 `.env`，填入 DASHSCOPE_API_KEY
- 交付物构建：`docker compose up -d`（验收日才需要）

## 文件位置约定
- 设计文档：docs/architecture.md、docs/database.md、docs/api.md
- 决策日志：docs/decisions.md
- 代码：app/（main.py 入口、models/ 数据模型、api/ 路由、services/ 业务逻辑、core/ 配置与通用能力）
- 演示页：demo/（Streamlit）
