"""Agent 的 Pydantic 请求/响应模型。"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AgentCreate(BaseModel):
    """创建 Agent 的请求体。"""

    name: str = Field(min_length=1, max_length=64, description="Agent 名称（唯一）")
    description: str = Field(default="", description="一句话描述")
    prompt_template: str = Field(default="", description="提示词模板（对话时拼装）")
    model_name: str = Field(default="qwen-turbo", description="模型名")
    temperature: float = Field(default=0.7, ge=0, le=2, description="温度（越低越克制）")
    max_tokens: int = Field(default=1024, ge=1, le=8192, description="单次回答最大 token")
    use_rag: bool = Field(default=False, description="是否走知识库检索")
    tools: list[str] = Field(default_factory=list, description="绑定工具名列表")
    knowledge_base_ids: list[int] = Field(default_factory=list, description="绑定的知识库 id 列表（模块2 起生效）")
    status: int = Field(default=1, ge=0, le=1, description="1=启用 0=停用")


class AgentUpdate(BaseModel):
    """修改 Agent 的请求体：只传想改的字段，其余保持不变。"""

    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    description: Optional[str] = None
    prompt_template: Optional[str] = None
    model_name: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0, le=2)
    max_tokens: Optional[int] = Field(default=None, ge=1, le=8192)
    use_rag: Optional[bool] = None
    tools: Optional[list[str]] = None
    knowledge_base_ids: Optional[list[int]] = None
    status: Optional[int] = Field(default=None, ge=0, le=1)


class AgentOut(BaseModel):
    """Agent 的响应模型（含绑定信息）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    prompt_template: str
    model_name: str
    temperature: float
    max_tokens: int
    use_rag: bool
    tools: list[str]
    knowledge_base_ids: list[int]
    status: int
    created_at: datetime
    updated_at: datetime


class AgentList(BaseModel):
    """分页列表响应。"""

    items: list[AgentOut]
    total: int