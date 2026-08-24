"""生成面试官视角的模块汇总 PDF（用 HTML + Chrome 无头打印，排版由浏览器引擎处理，中文断行完美）。

用法（以后每个模块结束时，把新模块的 content 追加进 MODULES 数组再运行）：
    python scripts/build_pdf.py
输出到 D:/agenthub/docs/ 下的 PDF。

注意：内容段落里的引号一律用全角『』，禁止在字符串内使用 ASCII 双引号（会截断 Python 字符串）。
"""

import re
import subprocess
import tempfile
from pathlib import Path

OUT_DIR = Path("D:/agenthub/docs")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 找本机 Chrome 或 Edge
_BROWSERS = [
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
]
BROWSER = next((p for p in _BROWSERS if Path(p).exists()), None)


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _para_to_html(para: str) -> str:
    """把一段文本渲染成 <p>：先整体 HTML 转义，再把 **粗体** 和 / *斜体* 标成标签。"""
    esc = _esc(para)
    esc = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc)
    esc = re.sub(r"\*(.+?)\*", r"<em>\1</em>", esc)
    stripped = para.lstrip()
    indent = len(para) - len(stripped)
    prefix = "&nbsp;" * (indent * 4)
    return f'<p class="li">{prefix}{esc.lstrip(" ")}</p>'


def _render_html(cfg: dict) -> str:
    body = []
    for section in cfg["sections"]:
        body.append(f'<h2>{_esc(section["h2"])}</h2>')
        for para in section["paragraphs"]:
            body.append(_para_to_html(para))
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<style>
  @page {{ size: A4; margin: 18mm 16mm; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: "Microsoft YaHei", sans-serif; color: #1f2937;
           font-size: 13.5px; line-height: 1.75; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; color: #111827; }}
  .subtitle {{ font-size: 12.5px; color: #6b7280; margin: 0 0 8px; border-bottom: 2px solid #2563eb;
                  padding-bottom: 10px; }}
  h2 {{ font-size: 15.5px; color: #2563eb; margin: 18px 0 6px; border-left: 4px solid #2563eb;
           padding-left: 10px; }}
  p {{ margin: 0 0 6px; text-align: justify; }}
  strong {{ color: #111827; }}
  em {{ color: #444; }}
</style></head><body>
  <h1>{_esc(cfg['title'])}</h1>
  <p class="subtitle">{_esc(cfg['subtitle'])}</p>
  {''.join(body)}
</body></html>"""


def make_pdf(cfg: dict) -> Path:
    html = _render_html(cfg)
    # Chrome headless 对中文文件路径支持不稳（可能 exit 13），因此全部用 ASCII 临时名，
    # 打印成功后再改名为正式（中文）文件名。
    tmp_html = OUT_DIR / "_tmp_module.html"
    tmp_pdf = OUT_DIR / "_tmp_module.pdf"
    tmp_html.write_text(html, encoding="utf-8")

    if not BROWSER:
        raise RuntimeError("未找到 Chrome/Edge，无法生成 PDF")

    # Chrome 在 Windows 上必须用 "--flag=value" 等号形式传参，空格分隔会报 exit 13。
    # 用独立 user-data-dir 避免与已打开的浏览器冲突。
    profile = tempfile.mkdtemp(prefix="agenthub_pdf_")
    subprocess.run(
        [
            BROWSER,
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            f"--user-data-dir={profile}",
            f"--print-to-pdf={tmp_pdf}",
            str(tmp_html),
        ],
        check=True, capture_output=True, timeout=60,
    )
    tmp_html.unlink()
    out_pdf = OUT_DIR / cfg["filename"]
    if out_pdf.exists():
        out_pdf.unlink()
    tmp_pdf.rename(out_pdf)
    return out_pdf


# =====================================================================
# 模块 1 + 模块 2 汇总内容（面试官视角 · 大白话版）
# =====================================================================

MODULES = [
    {
        "filename": "agenthub-面试问答-模块1-模块2.pdf",
        "title": "AgentHub 面试问答：模块 1 & 模块 2",
        "subtitle": "面向『AI Agent 研发工程师-后端』岗位 · 一份能直接背诵的项目话术（大白话版）",
        "sections": [
            {"h2": "一、项目全景：AgentHub 是什么",
             "paragraphs": [
                "**先补一个基础概念：什么是 Dify？** Dify 是一个开源工具，让不懂编程的人也能搭出 AI 助手（点几个按钮、传几份资料，就能做一个会聊天的机器人）。它本质是个 AI 应用开发平台。",
                "**AgentHub 就是简化版的 Dify**——我们自己从零写一个类似的东西（后端部分）：能创建多个 AI 助手（Agent）、给每个助手配上私有的知识资料和工具，再用一个统一接口对外提供对话服务。",
                "为什么要仿照 Dify 做：目标岗位是『Agent 平台后端』。做品类相同的产品，面试官一眼看懂你在做什么，直接进入技术细节。",
                "技术栈（JD 八项必须全落地）：FastAPI + MySQL + Redis + Chroma + Elasticsearch + 阿里云百炼大模型（OpenAI 兼容端点）+ Go 切分微服务 + 自有零依赖控制台。",
             ]},
            {"h2": "二、模块 1：Agent 管理",
             "paragraphs": [
                "**它解决什么问题**：我们要能创建、管理很多个 AI 助手。每个助手就是一张配置卡——它叫什么名字、告诉它该用什么语气和规则回答（提示词）、让它能查哪些知识资料、能用哪些工具、用哪套模型参数。把这些配置管好，后面的对话、知识库才有具体对象。",
                "**先解释几个词**：",
                "Agent（AI 助手）：一个装了大脑模型、一份人设说明、若干资料和工具的『虚拟员工』。",
                "提示词（Prompt）：你写给助手的『岗位说明书』，告诉它该怎么回答问题。",
                "知识库绑定：告诉这个助手『你遇到问题时，可以去查哪些资料』。",
                "**怎么实现的（流程）**：前端页面点按钮 → 发 HTTP 请求 → FastAPI 收到 → 校验数据格式和业务规则（重名不行、绑定的知识库得真实存在）→ 存进 MySQL 数据库 → 返回结果。",
                "**用到的技术（大白话）**：",
                "SQLAlchemy：一款把数据库表变成 Python 对象的工具。不用手写 SQL 语句，像操作对象一样增删改查，还防注入攻击。",
                "Pydantic：一款自动校验数据格式的工具。前端传来的 JSON 里某个字段类型错了（比如温度填了 5，应该 0~2），它会自动拦住并告诉你是哪里错了。",
                "Swagger：FastAPI 自带的一本可视化接口说明书，浏览器打开就能看到所有接口，还能直接点击发请求测试——省去装 Postman。",
                "**为什么用这些，比其它选择强在哪**：",
                "为什么用 FastAPI 不用 Django：Django 功能全但很重（自带后台管理、模板引擎等一堆我们不需要的），做个纯接口用它像开着货车买奶茶。FastAPI 轻、快（异步）、自带文档和校验，正好对味。",
                "为什么用 ORM 不用手写 SQL：手写 SQL 容易出错、难维护、有注入风险；用 ORM 代码更可读、可复用。我们 6 张小表，不值得引入重量级的数据库迁移工具（这也是面试可讲的范围收敛）。",
                "**最终效果**：在 /ui 控制台能创建、搜索、编辑、删除 AI 助手；Swagger 里也能手动调通增删改查；自动化测试覆盖了重名报错、找不到报 404 这类边界。",
             ]},
            {"h2": "三、模块 2：知识库管理",
             "paragraphs": [
                "**它解决什么问题**：想让助手回答问题时『有据可依』（不是瞎编），得先给它喂资料。模块 2 就是把用户上传的 PDF / TXT / MD 文档，变成助手能查的数据库，为后面对话时『翻资料回答』做准备。",
                "**先解释几个词**：",
                "RAG（检索增强生成）：一句话理解——先查再答。助手回答前，先从你给的资料里找到相关内容，再看这些内容回答。这样不会凭空瞎编，答案有出处。",
                "向量（Embedding）：把一句话转换成一串数字（几百个数字组成一组叫向量）。当你想判断两句话像不像，就比它们对应数字串的方向近不近。这就是计算机理解语义的方式。",
                "向量库：专门存这些数字串的地方，能快速找出哪串数字跟我要的最像。类似一个极速的找近似工具。",
                "切块（Chunking）：一篇长文档没法整篇硬塞给模型，得切成一小段一小段（每段一两百字），每段单独转成向量。就像把一本厚书先拆成一篇篇，再分别编上号。",
                "**怎么实现的（完整链路）**：",
                "1) 上传文档（前端选文件，后端只收 pdf / txt / md 三种）",
                "2) 把文档里的文字提取出来（PDF 用 pypdf 逐页抽取，txt / md 直接读）",
                "3) 调 Go 切分服务，把长文本切成一段段（chunk）",
                "4) 每段用百炼 text-embedding-v4 转成向量",
                "5) 把段落原文 + 向量 + 编号一起存进向量库 Chroma",
                "6) MySQL 只记台账（哪份文档、处理完没有、切了几段），不存正文",
                "另提供检索接口：把用户的提问也转成向量，去向量库里找最接近的段落返回。",
                "**为什么用 Go 做切分服务（JD 点名要求，重点讲）**：",
                "岗位 JD 明确写了要 Go，但我的主栈是 Python。策略不是转去学 Go，而是交付一个约 130 行的纯文本切分小服务，面试话术是『主栈 Python，Go 也能独立交付简单服务』。",
                "为什么切分用 Go 合适：切分是无状态、纯计算的活（进来一段文字，出去几段），Go 恰好擅长这种高并发、轻量、启动快的服务；而且单文件就能运行，不依赖一堆环境。",
                "边界：Go 只做纯文本切块（收到 /chunk 请求，返回切好的块），不碰 PDF 解析、不碰向量、不存数据——那些重活留给 Python，让 Go 保持小而清晰。",
                "**为什么用 Chroma 而不是 Milvus（面试高频）**：",
                "Chroma：轻量向量库，装个 Python 库就能用，数据存在本地文件夹，单机开发零门槛。",
                "Milvus：工业级分布式向量库，性能超强但部署很重（要起好几个组件）。",
                "我们这个项目单机开发、数据量小，Chroma 是够用且最省事的选择；把 Milvus 写进 README 的后续规划，体现我懂两者权衡。",
                "**切块策略（RAG 面试必考）**：不是死板按字数切。我们按文档的自然结构切：先按空行分段落 → 段内按行 → 行内按句号问号切句 → 太长的句子才硬切。每段不超过 500 字；相邻两段让前一段的末尾 50 字重叠到后一段开头，防止一句话被从中间切断丢语义。",
                "**检索实现（字面先行 + 语义兜底，按需求定制）**：",
                "1) 把提问拆成几个关键词，先在文档里检查这些词是否真实存在",
                "2) 所有关键词都不存在 → 直接返回『没找到』（比如搜红烧肉，库里没这个词，就明确告诉你没有，而不是硬凑一条）",
                "3) 关键词存在 → 再走向量找最相关的段落，只返回既包含关键词、语义又相近的块",
                "为什么这么做：纯向量检索对完全无关的词也会矮子里拔将军硬推几条，用户会觉得我搜红烧肉你也能搜出东西？先做字面验证，结果更可信、更可控。",
             ]},
            {"h2": "四、两个模块共通的工程亮点",
             "paragraphs": [
                "一次只做一个功能，做完提交：每个模块完成后先跑通自动化测试，再用中文写 commit 消息提交一次、推到 GitHub。这样出错能回滚，commit 历史也清清楚楚（初始化 → 助手管理 → 知识库），面试官看得出来是一步步踏实做出来的，不是一次成型。",
                "API Key 不泄露：真正的百炼密钥只存在本机 .env 文件里（已被 .gitignore 忽略，不会进 GitHub）；仓库里只放一个带占位符的 .env.example。还配了 git 钩子，万一不小心想把 .env 提交上去，直接拦截报错。这条对要公开的项目很重要。",
                "模型抽象层：项目里调大模型和调向量模型的地方都集中在一个文件里（core/llm.py）。哪天想换模型厂商，改一行配置就行，业务代码不用动。这是给面试官看的：我懂怎么接大模型、怎么留扩展。",
                "都留了开关和接口：Agent 配置里有个『是否检索』开关，为下个模块（对话时带知识）做准备，一步步推进、每步可验收。",
                "适配 8GB 开发机：内存大户 Elasticsearch 推迟到最后才装，并限制它只用 512MB 内存；开发期用本机软件而非常驻 Docker；Go 小服务用一条命令就能跑。",
             ]},
            {"h2": "五、验收结果（真实数字）",
             "paragraphs": [
                "自动化测试：pytest 全量 15 个用例通过（助手管理 + 知识库上传 / 检索 / 删除 + 接口冒烟测试 + 控制台可访问）。",
                "端到端实测：控制台里真实建知识库 → 上传 TXT / PDF → 看到切成几块 → 检索能命中相关内容、搜无关词返回没找到，全部验证过；Swagger 手动调通全部接口。",
                "成本：开发期向量调用花费约 0.0004 元量级，几乎可忽略。",
             ]},
        ],
    }
]


# =====================================================================
# 模块 3 汇总内容（面试官视角 · 大白话版）
# =====================================================================

MODULE3 = {
    "filename": "agenthub-面试问答-模块3-对话服务.pdf",
    "title": "AgentHub 面试问答：模块 3 · 对话服务",
    "subtitle": "面向『AI Agent 研发工程师-后端』岗位 · 一份能直接背诵的项目话术（大白话版）",
    "sections": [
        {"h2": "一、这个模块解决什么问题",
         "paragraphs": [
            "前两个模块做好了『助手配置』和『知识资料』，但助手还不会说话。模块 3 就是打通最后一公里：用户发一句话 → 平台交给大模型 → 把回答送回来。",
            "这是整个平台的门面接口：外部系统、控制台、演示页，都通过同一个接口 POST /api/chat 跟 Agent 对话。JD 里『统一 RESTful API 对外提供对话服务』说的就是它。",
            "一个重要认知（面试必讲）：**大模型本身没有记忆**。你每次调用它，它只看得见你这次发给它的内容。所谓多轮对话，本质是『把之前聊过的也塞进去再发一次』——这件事由我们的后端来做（模块 4 的会话管理）。",
         ]},
        {"h2": "二、先解释几个词（大白话）",
         "paragraphs": [
            "**messages（消息列表）**：调大模型时传的『对话记录』，每条带一个角色 role。三种角色：system（人设/规则，比如『你是客服，回答要简洁』）、user（用户说的话）、assistant（助手之前说过的话）。",
            "**system 提示词**：给模型的『岗位说明书』。我们存在 agents 表的 prompt_template 字段里，每个 Agent 可以有不同人设——同一个底座模型，配上不同说明书就是不同的助手。",
            "**temperature（温度）**：控制回答的『放飞程度』。0.2 很严谨（适合客服），1.2 很发散（适合创意写作）。存在 Agent 配置里，创建时可选。",
            "**max_tokens**：限制回答最多多少字（token 约等于半个到一个字），防止回答太长又费钱。",
         ]},
        {"h2": "三、怎么实现的（一次对话的完整流程）",
         "paragraphs": [
            "1) 前端把 {agent_id, session_id, message} 发给 POST /api/chat",
            "2) 编排层先查这个 agent_id 存不存在（不存在返回 404）",
            "3) 取出它的配置：提示词模板、模型名、温度、max_tokens",
            "4) 拼 messages = [一条 system 人设, 一条 user 用户的话]",
            "5) 用 Agent 自己的模型参数调百炼（qwen-turbo 等）",
            "6) 把回答包成 {reply, session_id, model} 返回；前端渲染成聊天气泡",
            "代码分层：api/chat.py 收请求 → services/chat_service.py 编排 → core/llm.py 统一调模型。跟前面模块同一套分层规矩。",
         ]},
        {"h2": "四、关键设计决策（为什么这么做）",
         "paragraphs": [
            "**编排骨架 + 预留插槽**：chat_service 里现在只有『取配置→拼人设→调模型』三步，但代码里明确注释了模块 4 在哪插历史、模块 5/6 在哪插检索结果。好处：后面加功能不动主结构，每一步都可单独验收。",
            "**人设来自 Agent 配置而非写死**：system 内容优先用 agents.prompt_template，没填就兜底一句『你是名叫 xx 的助手』。这样『平台管配置、模型只管说话』，这正是 Agent 平台和普通聊天机器人的本质区别。",
            "**模型参数跟着 Agent 走**：不同 Agent 可配不同模型（qwen-turbo 便宜调试 / qwen-plus 更强演示）、不同温度。调度时读它的配置传给 llm.chat()，而不是全局一刀切。",
            "**session_id 前端生成、后端认账**：会话号由前端生成（UUID 式随机串），后端收下并原样返回。模块 3 还没存历史，但身份已经定了——模块 4 的 Redis 会话直接用它当 key，平滑升级。",
            "**继续走模型抽象层**：调对话模型和调向量模型一样，都收敛在 core/llm.py。换厂商改 .env 即可，业务代码零改动。",
         ]},
        {"h2": "五、验收结果（真实数字）",
         "paragraphs": [
            "自动化测试新增 3 个：真实调用 qwen 对话拿到非空回答且体现人设（『客服』关键词）；不存在的 agent_id 返回 404；没填提示词模板也能用兜底人设正常答。全量 18 个测试通过。",
            "端到端实测：控制台选 Agent → 发消息 → 气泡显示中文回答，全链路 200。",
            "成本：qwen-turbo 单轮对话约几百 token，成本可忽略量级。",
         ]},
        {"h2": "六、当前局限与下一步（主动交代，面试加分）",
         "paragraphs": [
            "**现在的助手是『金鱼记忆』**：问『我叫小明』再问『我叫什么』，它答不上来——因为每次只发了当前这一句，没有历史。这不是 bug，是多轮上下文还没接（正是模块 4 的活）。",
            "**也没接知识库**：Agent 配置里有 use_rag 开关但现在还没生效，检索结果拼进提示词是模块 5/6 的事。架构上插槽已留好。",
            "这样一步步来的原因：先把最短链路（配置→人设→模型→回答）跑通验稳，再逐个往链路里加能力。每步可测试、可回滚、可演示。",
         ]},
    ],
}


def main() -> None:
    for cfg in MODULES + [MODULE3]:
        path = make_pdf(cfg)
        print("已生成：", path)


if __name__ == "__main__":
    main()