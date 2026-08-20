"""
LLM 适配器
统一的 LLM 调用接口，支持 Mock 和 OpenAI 两种后端
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


# ============================================================
# 通用数据结构
# ============================================================

@dataclass
class LLMResponse:
    """LLM 响应"""
    content: str
    model: str = ""
    tokens_used: int = 0
    latency_ms: float = 0.0
    finish_reason: str = "stop"
    raw_response: Any = None


class LLMError(Exception):
    """LLM 调用通用异常"""
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


# ============================================================
# 抽象基类
# ============================================================

class BaseLLMAdapter(ABC):
    """LLM 适配器抽象基类"""
    
    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 500,
        **kwargs
    ) -> LLMResponse:
        """发送对话请求，返回统一响应"""
        pass
    
    @property
    @abstractmethod
    def model_name(self) -> str:
        """返回当前使用的模型名"""
        pass


# ============================================================
# Mock 适配器（开发测试用）
# ============================================================

class MockLLMAdapter(BaseLLMAdapter):
    """
    Mock LLM 适配器
    支持三种模式：
    - static: 始终返回固定响应
    - scripted: 按顺序返回预设响应列表
    - callback: 根据输入动态生成响应
    """
    
    def __init__(
        self,
        mode: str = "static",
        static_response: Optional[LLMResponse] = None,
        scripted_responses: Optional[List[LLMResponse]] = None,
        callback: Optional[callable] = None,
        simulate_latency_ms: float = 100.0,
        model: str = "mock-llm",
    ):
        self._mode = mode
        self._model = model
        self._call_count = 0
        self._simulate_latency_ms = simulate_latency_ms
        
        # static 模式
        self._static_response = static_response or LLMResponse(
            content='{"selected_model": "gpt-4", "confidence": 0.9, "reasoning": "mock decision"}',
            model=model,
            tokens_used=100,
            latency_ms=simulate_latency_ms,
        )
        
        # scripted 模式
        self._scripted_responses = scripted_responses or []
        self._script_index = 0
        
        # callback 模式
        self._callback = callback
        
        # 历史记录
        self.history: List[Dict[str, Any]] = []
    
    @property
    def model_name(self) -> str:
        return self._model
    
    @property
    def call_count(self) -> int:
        return self._call_count
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 500,
        **kwargs
    ) -> LLMResponse:
        self._call_count += 1
        
        self.history.append({
            "call": self._call_count,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })
        
        if self._mode == "static":
            response = self._static_response
        elif self._mode == "scripted":
            if self._script_index < len(self._scripted_responses):
                response = self._scripted_responses[self._script_index]
                self._script_index += 1
            else:
                response = self._scripted_responses[-1] if self._scripted_responses else self._static_response
        elif self._mode == "callback":
            if self._callback:
                response = self._callback(messages, self._call_count)
            else:
                response = self._static_response
        else:
            response = self._static_response
        
        response.latency_ms = self._simulate_latency_ms
        
        return response
    
    def reset(self):
        self._call_count = 0
        self._script_index = 0
        self.history.clear()
    
    def set_response(self, response: LLMResponse):
        self._static_response = response
    
    @classmethod
    def from_json_file(cls, filepath: str) -> "MockLLMAdapter":
        import json
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        responses = []
        for item in data:
            responses.append(LLMResponse(
                content=item.get("content", ""),
                model=item.get("model", "mock-llm"),
                tokens_used=item.get("tokens_used", 0),
                finish_reason=item.get("finish_reason", "stop"),
            ))
        
        return cls(mode="scripted", scripted_responses=responses)
    
    @classmethod
    def decision_mock(cls) -> "MockLLMAdapter":
        return cls(
            mode="static",
            static_response=LLMResponse(
                content='{"selected_model": "gpt-4", "confidence": 0.9, "reasoning": "任务包含代码生成，需要强模型支持", "alternative": "claude-opus", "risk_assessment": "低风险"}',
                model="mock-llm",
                tokens_used=150,
            ),
            model="mock-decision-llm",
        )
    
    @classmethod
    def cost_saving_mock(cls) -> "MockLLMAdapter":
        return cls(
            mode="static",
            static_response=LLMResponse(
                content='{"selected_model": "gpt-3.5-turbo", "confidence": 0.85, "reasoning": "简单问答任务，使用低成本模型即可", "alternative": "local-llama-8b", "risk_assessment": "低风险"}',
                model="mock-llm",
                tokens_used=120,
            ),
            model="mock-decision-llm",
        )
    
    @classmethod
    def privacy_mock(cls) -> "MockLLMAdapter":
        return cls(
            mode="static",
            static_response=LLMResponse(
                content='{"selected_model": "local-private-llm-v2", "confidence": 0.95, "reasoning": "检测到 PII 信息，必须使用本地隐私模型", "alternative": "tee-gpt-4", "risk_assessment": "高风险 - 包含个人敏感信息"}',
                model="mock-llm",
                tokens_used=180,
            ),
            model="mock-decision-llm",
        )
    
    @classmethod
    def fallback_mock(cls) -> "MockLLMAdapter":
        def error_callback(messages, call_count):
            raise LLMError("Mock LLM timeout", retryable=False)
        
        return cls(
            mode="callback",
            callback=error_callback,
            model="mock-decision-llm",
        )
    
    @classmethod
    def malformed_json_mock(cls) -> "MockLLMAdapter":
        return cls(
            mode="static",
            static_response=LLMResponse(
                content="抱歉，我无法做出决策，请重试。",
                model="mock-llm",
                tokens_used=50,
            ),
            model="mock-decision-llm",
        )


# ============================================================
# OpenAI 适配器（生产用）
# ============================================================

class OpenAIAdapter(BaseLLMAdapter):
    """OpenAI API 适配器"""
    
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self._model = model
        self._api_key = api_key
        self._base_url = base_url
        self._timeout = timeout
        self._client = None
    
    @property
    def model_name(self) -> str:
        return self._model
    
    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError:
                raise ImportError("openai 包未安装，请执行 pip install openai")
            
            kwargs = {"api_key": self._api_key, "timeout": self._timeout}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = OpenAI(**kwargs)
        
        return self._client
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 500,
        **kwargs
    ) -> LLMResponse:
        import time
        
        client = self._get_client()
        start = time.time()
        
        try:
            completion = client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
            latency = (time.time() - start) * 1000
            
            choice = completion.choices[0]
            usage = completion.usage
            
            return LLMResponse(
                content=choice.message.content or "",
                model=completion.model,
                tokens_used=usage.total_tokens if usage else 0,
                latency_ms=latency,
                finish_reason=choice.finish_reason or "stop",
                raw_response=completion,
            )
        except Exception as e:
            raise LLMError(message=str(e), retryable=_is_retryable(e)) from e


def _is_retryable(error: Exception) -> bool:
    error_str = str(error).lower()
    retryable_keywords = ["timeout", "rate limit", "server error", "503", "502", "429"]
    return any(kw in error_str for kw in retryable_keywords)