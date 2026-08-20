"""
Agent Router - 请求数据模型
定义统一的任务输入格式，支持对话消息、工具调用、策略偏好等
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from datetime import datetime


class MessageRole(str, Enum):
    """消息角色枚举"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class Message(BaseModel):
    """单条消息"""
    role: MessageRole = Field(..., description="消息角色")
    content: str = Field(..., description="消息内容")
    name: Optional[str] = Field(None, description="发送者名称（可选）")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "role": "user",
                "content": "What is the capital of France?"
            }
        }
    }


class ToolDefinition(BaseModel):
    """工具定义(兼容OpenAI Function Calling格式)"""
    type: str = Field(default="function", description="工具类型")
    function: dict[str, object] = Field(..., description="函数定义")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather for a city",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "city": {"type": "string"}
                        }
                    }
                }
            }
        }
    }


class RoutingPolicy(str, Enum):
    """路由策略枚举"""
    COST_FIRST = "cost_first"           # 成本优先
    QUALITY_FIRST = "quality_first"     # 质量优先
    PRIVACY_STRICT = "privacy_strict"   # 隐私严格
    BALANCED = "balanced"               # 均衡策略
    FIXED_STRONG = "fixed_strong"       # 固定强模型（基线）
    FIXED_CHEAP = "fixed_cheap"         # 固定低成本（基线）


class BudgetConstraint(BaseModel):
    """预算约束"""
    max_cost_usd: Optional[float] = Field(None, description="最大成本（美元）")
    max_latency_ms: Optional[float] = Field(None, description="最大延迟（毫秒）")
    preferred_models: Optional[list[str]] = Field(None, description="偏好模型白名单")
    blocked_models: Optional[list[str]] = Field(None, description="禁止模型黑名单")


class RouterRequest(BaseModel):
    """
    路由请求 - 统一任务入口
    
    包含完整的Agent任务信息和路由约束
    """
    # 请求标识
    request_id: str = Field(
        default_factory=lambda: f"req_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        description="请求唯一标识"
    )
    
    # 任务内容
    messages: list[Message] = Field(
        ..., 
        description="对话消息列表",
        min_length=1
    )
    tools: Optional[list[ToolDefinition]] = Field(
        default=None, 
        description="可用工具定义列表"
    )
    
    # 路由约束
    policy: RoutingPolicy = Field(
        default=RoutingPolicy.BALANCED,
        description="路由策略"
    )
    budget: Optional[BudgetConstraint] = Field(
        default=None,
        description="预算约束"
    )
    
    # 元数据
    metadata: Optional[dict[str, object]] = Field(
        default=None,
        description="任务元数据（如隐私标签、领域标识等）"
    )
    trace_id: Optional[str] = Field(
        default=None,
        description="链路追踪ID(为空时自动生成)"
    )
    
    def get_full_text(self) -> str:
        """获取完整的对话文本（用于特征提取）"""
        return "\n".join([msg.content for msg in self.messages])
    
    def get_last_message(self) -> Message:
        """获取最后一条用户消息"""
        return self.messages[-1]
    
    def has_tools(self) -> bool:
        """是否包含工具定义"""
        return self.tools is not None and len(self.tools) > 0
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "request_id": "req_20240101120000",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a helpful assistant."
                    },
                    {
                        "role": "user",
                        "content": "帮我重构这段Python代码,添加类型注解"
                    }
                ],
                "tools": None,
                "policy": "quality_first",
                "budget": {
                    "max_cost_usd": 0.1,
                    "max_latency_ms": 5000
                },
                "metadata": {
                    "domain": "code_review",
                    "complexity_hint": "high"
                }
            }
        }
    }