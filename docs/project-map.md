# 项目目录地图（给"懂 Java、刚接触 Python"的人）

> 目标：让你打开这个项目不再迷路。用你熟悉的 Java/Spring 分层做对照，
> 每个目录/文件"在业务里是干嘛的"一句话说清。

## 0. 最核心的一句话

**`app/` 是整个后端（Python/FastAPI），`web/` 是前端（控制台），
`chunker/` 是一个独立的 Go 微服务。** 三个主要代码区，各自独立。

---

## 1. 一张表：Java 分层 ↔ 本项目

| 你熟悉的 Java/Spring | 本项目的对应 | 业务里干嘛 |
|---|---|---|
| `Controller`（控制层/接口层） | `app/api/` | 收 HTTP 请求、返回响应（路由） |
| `Service`（业务逻辑层） | `app/services/` | 真正干活：校验、存取数据、算返回值 |
| `Mapper` / `DAO`（数据访问层） | `app/core/db.py` + `app/models/` | 连数据库、把表映射成对象 |
| `Entity`（实体类/表对象） | `app/models/` | 每个类 = 一张数据库表 |
| `DTO` / `VO`（传参/返回值格式） | `app/schemas/` | 接口"收什么、吐什么"的格式说明书 |
| `Config` / `application.yml` | `app/core/config.py` + `.env` | 一切配置集中管理 |
| `Application` 启动类 | `app/main.py` | 程序入口，拼装所有模块 |
| 各种 Util / 通用工具 | `app/core/` | 大模型封装、调 Go 客户端、数据库连接 |
| 前端页面 | `web/` | 原生 HTML/JS 控制台（[`/ui`](http://127.0.0.1:8000/ui)） |

> Python 没有 Java 那种"强制分层约定"。这套 api → services → models → schemas 的分层
> 是我们（照 FastAPI 生态习惯）自己定的"规矩"，好处和 Spring 一样：各层职责单一、好测好改。

---

## 2. 自顶向下逐目录认一遍

```
agenthub/
├── app/                    ← 【后端】Python + FastAPI（你主营业务在这）
│   ├── main.py             ← 程序入口：创建 FastAPI 应用、把各模块路由挂上来、托管前端
│   ├── api/                ← 【Controller】接口层：收请求/返回响应（最薄的一层）
│   │   ├── agents.py       ←     Agent 模块的 5 个接口（增删改查）
│   │   └── knowledge.py    ←     知识库/文档/检索的 6 个接口
│   ├── services/           ← 【Service】业务层：真正干活的地方
│   │   ├── agent_service.py    ←    助手的增删改查逻辑
│   │   ├── knowledge_service.py←    上传文档→切块→向量→入库、检索
│   │   └── vector_store.py     ←    操作向量库 Chroma 的封装
│   ├── models/             ← 【Entity】数据模型：每个类 = 一张 MySQL 表
│   │   ├── agent.py        ←     agents 表 + 绑定关系表
│   │   └── knowledge.py    ←     知识库表 + 文档台账表
│   ├── schemas/            ← 【DTO/VO】接口收发数据的格式
│   │   ├── agent.py
│   │   └── knowledge.py
│   └── core/               ← 【工具/配置】通用能力
│       ├── config.py       ←     读 .env 配置的总源头
│       ├── db.py           ←     数据库连接 + 会话管理
│       ├── llm.py          ←     大模型/向量模型封装（换厂商只改 .env）
│       └── chunker.py      ←     调 Go 切分服务的客户端
│
├── web/                    ← 【前端】控制台（是你说的"前端代码"）
│   ├── index.html          ←     页面结构（骨架）
│   ├── style.css           ←     样式（好看）
│   └── app.js              ←     逻辑（点按钮 → fetch → 调后端接口）
│
├── chunker/                ← 一个独立的 Go 微服务（切文本用的，不是 Python）
│   ├── main.go             ← Go 代码：HTTP POST /chunk 把长文切成块
│   └── go.mod              ← Go 的依赖/模块声明（相当于 requirements.txt）
│
├── demo/                   ← 收尾阶段的 Streamlit 演示页（暂时空着）
├── docs/                   ← 设计/说明文档（architecture 架构、database 表、api 接口……）
├── tests/                  ← 自动化测试（test_agents / test_knowledge / test_health）
├── scripts/                ← 辅助脚本（build_pdf.py 生成面试 PDF）
├── data/                   ← 运行时数据：Chroma 向量库落盘处（已 gitignore）
├── .env                    ← 【密钥！】百炼 API Key（本地独有，绝不提交）
├── requirements.txt        ← Python 依赖清单（相当于 Maven 的 pom.xml）
├── .gitignore / .gitattributes / .githooks/  ← git 相关配置
└── docker-compose.yml      ← 收尾阶段"一键起所有服务"的编排
```

---

## 3. 一个请求在各层怎么流动（对照 Java 就更直观）

以"创建助手"为例：

```
前端 web/app.js 点"创建"
   ↓ 发 POST /api/agents（JSON）
app/api/agents.py        → 我接收请求、交给你（Controller）
   ↓
app/services/agent_service.py → 查重名、建数据、写绑定、落库（Service）
   ↓
app/models/agent.py      → 用类把"要存的内容"翻译成一行数据库数据（Entity/Mapper）
   ↓
MySQL agents 表            → 真的存进去
   ↓
（原路返回）响应 JSON → 前端显示"创建成功"
```

> 记法：**api 管"接"，services 管"办"，models 管"存"，schemas 管"格式"**。
> 开发时改逻辑 = 改 services；加接口 = 在 api 里加一个函数；改表 = 改 models。

---

## 4. 常问的几个"这个文件是干嘛的"

| 文件 | 答案 |
|---|---|
| `__init__.py`（到处都是）| 告诉 Python"这个目录是一个可导入的包"。空文件也行，就是"包标记" |
| `.env` / `.env.example` | 真实密钥 / 占位模板（前者被忽略，后者入库） |
| `conftest.py`（根部）| pytest 的钩子文件，让测试能找到 app 代码 |
| `go.mod` | Go 的模块声明（类似 requirements.txt） |
| `uvicorn` 命令 | 启动脚本（相当于 `java -jar xx.jar` 那一步） |

---

## 5. 怎么快速确认"哪个是后端、哪个是前端"

- 看目录名：`app/` 后端、`web/` 前端、`chunker/` Go 服务、`demo/` 演示页。
- 看技术：`.py` 全是后端 Python；`.html/.css/.js`（在 web/）是前端；`.go` 是 Go。
- 看端口：`8000` = 主后端（FastAPI），`8080` = Go 切分服务。

---

## 6. Python 装饰器（`@` 注解）速查

> 你从 Java 来，看到代码里一堆 `@` 一定眼熟。但 Python 的 `@` 叫**装饰器**，
> 不是 Java 那种"元数据注解"，而是**真的给函数套一层壳**的代码。
> 好在**用法像**：都是写在函数上面，给函数赋予特殊身份。当 Java 注解记即可，知道"它真的会改函数"更准。

### 先分清概念

| | Java 注解 | Python 装饰器 |
|---|---|---|
| 本质 | 元数据标记（本身不改行为） | 真正包裹函数的代码（定义时当场生效） |
| 例子 | `@GetMapping` | `@router.get` |
| 谁消费 | 框架靠反射读 | 定义时就注册/包装 |

### 本项目实际用到的 6 个

| 装饰器 | 出现在哪 | 干嘛的（大白话） | Java 类比 |
|---|---|---|---|
| `@router.get/post/put/delete` | `app/api/*.py` | 注册 HTTP 接口：下面的函数收到对应路径/方法的请求才被调用 | `@GetMapping` 等 |
| `@app.get` | `app/main.py` | 应用级接口（`/health`），同上但挂在整个应用上 | Application 上的路由 |
| `@property` | `app/core/config.py` | 把"方法"变成"字段"：调用不用加括号，像读属性一样取值 | getter |
| `@lru_cache` | `app/core/config.py` | 缓存函数结果：整个进程只算一次，之后直接返回缓存 | 手动单例/缓存 |
| `@asynccontextmanager` | `app/main.py` | 把生成器变成"启动/关闭钩子"：yield 前=启动时做，yield 后=关闭时做 | `@PostConstruct` |
| `@pytest.fixture` | `tests/*.py` | 测试里造"现成工具"，别的测试函数声明参数时自动注入 | `@BeforeAll` + 注入 |

### 逐个看真实例子

**1. `@router.post` —— 注册接口（最重要）**
```python
@router.post("", response_model=AgentOut, status_code=201, summary="创建 Agent")
def create_agent(payload: AgentCreate, db: Session = Depends(get_db)):
    return agent_service.create_agent(db, payload)
```
> 意思是：下面这个函数，负责响应 `POST /api/agents`。没这行，它就只是个普通函数，
> 永远不会被网络请求触发。这行= Java 的 `@PostMapping("/api/agents")`。

**2. `@property` —— 方法当字段读**
```python
@property
def mysql_url(self) -> str:
    return f"mysql+pymysql://..."
```
> 调用：`settings.mysql_url`（**没有括号**）。普通方法得写 `settings.mysql_url()`。
> 加了它，用起来就像读一个"预先拼好的配置字段"，但其实是现算的。≈ Java 的 `getMysqlUrl()`。

**3. `@lru_cache` —— 缓存/单例**
```python
@lru_cache
def get_settings() -> Settings:
    return Settings()
```
> 第一次调用真执行，之后就返回记住的结果。保证整个项目只有一个配置对象，省资源。

**4. `@asynccontextmanager` —— 启动/关闭钩子**
```python
@asynccontextmanager
async def lifespan(app):
    init_db()      # ← 服务启动时执行（建表）
    yield          # ← 服务运行期间"挂起"
                   # ← 服务关闭时执行（可在这清理）
```
> ≈ Java 的 `@PostConstruct`（启动时初始化）。

**5. `@pytest.fixture` —— 测试注入**
```python
@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c

def test_health(client):   # ← 参数里写 client，框架自动把上面的东西传进来
    ...
```
> scope="session"：整个测试会话只造一次。≈ Java 的 `@BeforeAll`（测试前准备一次）+ 自动注入。

### 记住用法：`@` 下面紧跟"这个函数是干嘛的"

打开 `app/api/agents.py`，你会发现每个函数上面都有一行 `@router.xxx`——
那一行就是"接口的登记表"：**方法 + 路径 + 返回格式 + 说明**，一行全写在上面。
看懂这一行，就懂这个接口。