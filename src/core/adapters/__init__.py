# src/core/adapters/__init__.py

"""
LLM 适配器模块
提供统一的 LLM 调用接口
"""

from src.core.adapters.llm_adapter import (
    BaseLLMAdapter,
    LLMResponse,
    LLMError,
    MockLLMAdapter,
    OpenAIAdapter,
)
from src.core.adapters.zhipu_adapter import ZhipuAdapter

__all__ = [
    "BaseLLMAdapter",
    "LLMResponse",
    "LLMError",
    "MockLLMAdapter",
    "OpenAIAdapter",
    "ZhipuAdapter",
]