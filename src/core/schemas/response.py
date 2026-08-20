"""
Agent Router - 响应数据模型
统一的输出格式，包含模型返回内容和完整路由凭证
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum

from .receipt import RouteReceipt
from .request import Message


class ResponseStatus(str, Enum):
    """响应状态枚举"""
    SUCCESS = "success"           # 成功
    PARTIAL_SUCCESS = "partial"   # 部分成功（如降级后完成）
    BLOCKED = "blocked"          # 被阻断（如隐私策略拒绝）
    FAILED = "failed"            # 失败
    TIMEOUT = "timeout"          # 超时


class ModelResponse(BaseModel):
    """模型返回内容"""
    content: str = Field(..., description="模型输出文本")
    finish_reason: Optional[str] = Field(None, description="结束原因")
    tokens_used: Optional[int] = Field(None, description="实际使用token数")
    model: str = Field(..., description="实际调用的模型")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "content": "The capital of France is Paris.",
                "finish_reason": "stop",
                "tokens_used": 25,
                "model": "gpt-3.5-turbo"
            }
        }
    }


class RouterResponse(BaseModel):
    """
    路由响应 - 统一输出格式
    
    将模型返回内容和完整路由凭证打包
    """
    # 响应标识
    response_id: str = Field(
        default_factory=lambda: f"resp_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        description="响应唯一ID"
    )
    request_id: str = Field(..., description="对应的请求ID")
    
    # 状态信息
    status: ResponseStatus = Field(..., description="响应状态")
    status_message: str = Field(default="", description="状态说明")
    
    # 模型响应
    model_response: Optional[ModelResponse] = Field(
        None, 
        description="模型返回内容（成功时填充）"
    )
    
    # 路由凭证（核心）
    receipt: RouteReceipt = Field(..., description="路由决策凭证")
    
    # 错误信息
    errors: list[str] = Field(default_factory=list, description="错误列表")
    warnings: list[str] = Field(default_factory=list, description="警告列表")
    
    # 阻断信息
    is_blocked: bool = Field(default=False, description="是否被阻断")
    block_reason: Optional[str] = Field(None, description="阻断原因")
    
    # 性能指标
    total_latency_ms: float = Field(default=0.0, description="总延迟")
    routing_latency_ms: float = Field(default=0.0, description="路由延迟")
    model_latency_ms: float = Field(default=0.0, description="模型推理延迟")
    
    # 时间戳
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")
    
    # 扩展信息
    extra: dict[str, object] = Field(default_factory=dict, description="扩展信息")
    
    def is_successful(self) -> bool:
        """是否成功"""
        return self.status in [ResponseStatus.SUCCESS, ResponseStatus.PARTIAL_SUCCESS]
    
    def get_display_output(self) -> str:
        """获取可展示的输出"""
        if self.status == ResponseStatus.BLOCKED:
            return f"[BLOCKED] {self.block_reason}"
        if self.model_response:
            return self.model_response.content
        return f"[{self.status.value}] {self.status_message}"
    
    def to_client_response(self) -> dict[str, object]:
        """
        转换为客户端响应格式(兼容OpenAI格式)
        """
        estimated = self.receipt.estimated_cost
        input_tokens = estimated.input_tokens if estimated else 0
        output_tokens = estimated.output_tokens if estimated else 0
        
        return {
            "id": self.response_id,
            "object": "chat.completion",
            "created": int(self.created_at.timestamp()),
            "model": self.receipt.selected_model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": self.model_response.content if self.model_response else ""
                    },
                    "finish_reason": self.model_response.finish_reason if self.model_response else "error"
                }
            ] if self.model_response else [],
            "usage": {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": (input_tokens or 0) + (output_tokens or 0)
            },
            "route_receipt": self.receipt.to_audit_log()  # 附带路由凭证
        }
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "response_id": "resp_20240101120000",
                "request_id": "req_20240101120000",
                "status": "success",
                "model_response": {
                    "content": "这是重构后的代码...",
                    "model": "local-private-llm-v2"
                },
                "receipt": {
                    "receipt_id": "rcpt_20240101120000",
                    "selected_model": "local-private-llm-v2",
                    "privacy_level": "high"
                },
                "total_latency_ms": 450.0,
                "routing_latency_ms": 5.2,
                "model_latency_ms": 444.8
            }
        }
    }