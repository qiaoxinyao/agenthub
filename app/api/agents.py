"""Agent 管理的 5 个 RESTful 接口。

【大白话】这一层很"薄"：只负责三件事——声明路由（什么方法+什么路径）、
接收请求参数、把活丢给 service 层做、把结果返回。真正的业务规则都在 service。
这样做的好处：接口层很干净，业务逻辑能单独复用和测试。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.agent import AgentCreate, AgentList, AgentOut, AgentUpdate
from app.services import agent_service

# 声明路由组：这个文件里所有接口路径都以 /agents 开头；tags 是在 Swagger 文档里的分组名
router = APIRouter(prefix="/agents", tags=["Agent 管理"])


# 装饰器含义：注册一个 POST 接口（路径 = /api/agents）；
# response_model 声明"成功返回的数据格式"；status_code=201 表示创建成功的 HTTP 状态码；
# summary 会显示在 Swagger 文档页上
@router.post("", response_model=AgentOut, status_code=201, summary="创建 Agent")
def create_agent(payload: AgentCreate, db: Session = Depends(get_db)):
    """创建助手。

    payload: AgentCreate —— FastAPI 会自动校验请求体格式，不对直接 422。
    db: Depends(get_db) —— 依赖注入：框架给每个请求发一个数据库会话，用完自动还。
    """
    return agent_service.create_agent(db, payload)


# 注册 GET 接口（路径 = /api/agents）：查询助手列表
@router.get("", response_model=AgentList, summary="查询 Agent 列表")
def list_agents(
    # Query() = 声明这是 URL 查询参数（?name=xx&page=1&size=20 那种）；ge/le 是范围校验
    name: str | None = Query(default=None, description="按名称模糊过滤"),
    page: int = Query(default=1, ge=1, description="页码，从 1 开始"),
    size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
):
    """查询助手列表（分页 + 可按名称过滤）。"""
    items, total = agent_service.list_agents(db, page=page, size=size, name=name)
    return {"items": items, "total": total}


# 注册 GET 接口（路径 = /api/agents/{agent_id}）：{agent_id} 是路径参数，
# 比如 /api/agents/5 就会把 5 传进函数的 agent_id 参数
@router.get("/{agent_id}", response_model=AgentOut, summary="查询单个 Agent 详情")
def get_agent(agent_id: int, db: Session = Depends(get_db)):
    """查询单个助手详情。"""
    return agent_service.get_agent(db, agent_id)


# 注册 PUT 接口（路径 = /api/agents/{agent_id}）：PUT 在 RESTful 里表示"修改"
@router.put("/{agent_id}", response_model=AgentOut, summary="修改 Agent（只改传了的字段）")
def update_agent(agent_id: int, payload: AgentUpdate, db: Session = Depends(get_db)):
    """修改助手。请求体里传了哪个字段就改哪个，没传的保持不变。"""
    return agent_service.update_agent(db, agent_id, payload)


# 注册 DELETE 接口（路径 = /api/agents/{agent_id}）；status_code=204 表示
# "删除成功且不返回任何内容"（HTTP 标准约定）
@router.delete("/{agent_id}", status_code=204, summary="删除 Agent")
def delete_agent(agent_id: int, db: Session = Depends(get_db)):
    """删除助手（级联清理绑定关系）。"""
    agent_service.delete_agent(db, agent_id)