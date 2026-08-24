"""Agent 的 Pydantic 请求/响应模型。

【大白话】这类文件是"数据传输的格式说明书"，分三种：
- AgentCreate：前端发来"创建助手"请求的标准格式（缺一个必填就报错）
- AgentUpdate：前端发来"修改助手"的标准格式（只传想改的字段）
- AgentOut：后端返回"一个助手"的标准格式（保证前端拿到的字段统一）
为什么要单独定义？让"接口收什么、吐什么"清清楚楚，省得前后端对不上。
"""

from datetime import datetime
from typing import Optional

# Field 用来给"必填/范围/默认值/说明"盖章；min_length/max_length/ge/le 都是校验规则
from pydantic import BaseModel, ConfigDict, Field


class AgentCreate(BaseModel):
    """创建 Agent 的请求体。"""

    # Field(min_length=1) = 至少 1 个字符，name 必填（没写 default 就是必填）
    name: str = Field(min_length=1, max_length=64, description="Agent 名称（唯一）")
    description: str = Field(default="", description="一句话描述")
    prompt_template: str = Field(default="", description="提示词模板（对话时拼装）")
    model_name: str = Field(default="qwen3.7-plus", description="模型名")
    temperature: float = Field(default=0.7, ge=0, le=2, description="温度（越低越克制）")  # ge=>=0 le=<=2
    max_tokens: int = Field(default=1024, ge=1, le=8192, description="单次回答最大 token")
    use_rag: bool = Field(default=False, description="是否走知识库检索")
    tools: list[str] = Field(default_factory=list, description="绑定工具名列表")
    # default_factory=list：每个请求拿一个"新的空列表"（不能 default=[]，那会共用同一个列表对象，有坑）
    knowledge_base_ids: list[int] = Field(default_factory=list, description="绑定的知识库 id 列表")
    status: int = Field(default=1, ge=0, le=1, description="1=启用 0=停用")


class AgentUpdate(BaseModel):
    """修改 Agent 的请求体：只传想改的字段，其余保持不变。

    【为什么全部 Optional + default=None】
    "Optional[名字] = None" 表示"这个字段可以不给"。
    给我们的接口语义：请求体里出现某个字段才更新它，没出现就不动。
    比如只传 {"temperature": 0.8}，就只改温度，别的全保留。
    """

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
    """Agent 的响应模型（含绑定信息）。是返回给前端的样子。"""

    # from_attributes=True：允许直接把"数据库对象"转成这个模型（省得手写转换）
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
    knowledge_base_ids: list[int]  # 注意：这个字段数据库表里没有，是由"绑定关系"算出来的（见 service）
    status: int
    created_at: datetime
    updated_at: datetime


class AgentList(BaseModel):
    """分页列表响应：一页数据 + 总数（前端做分页要靠 total）。"""

    items: list[AgentOut]
    total: int