"""
OpenAI 兼容 API 适配器
支持 OpenAI / DeepSeek / 通义千问 / 零一万物 等兼容接口
"""
import time
from typing import List, Dict, Any, Optional

from src.core.adapters.llm_adapter import BaseLLMAdapter, LLMResponse, LLMError


class OpenAICompatibleAdapter(BaseLLMAdapter):
    """
    OpenAI 兼容 API 适配器

    用法:
        # DeepSeek
        adapter = OpenAICompatibleAdapter(
            api_key="sk-xxx",
            model="deepseek-chat",
            base_url="https://api.deepseek.com/v1",
        )

        # 通义千问
        adapter = OpenAICompatibleAdapter(
            api_key="sk-xxx",
            model="qwen-turbo",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )

        # OpenAI
        adapter = OpenAICompatibleAdapter(
            api_key="sk-xxx",
            model="gpt-4o-mini",
        )
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self._model = model
        self.api_key = api_key
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self.timeout = timeout
        self._client = None

    @property
    def model_name(self) -> str:
        return self._model

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError:
                raise ImportError("请安装 openai: pip install openai")

            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 500,
        **kwargs
    ) -> LLMResponse:
        client = self._get_client()
        start = time.time()

        try:
            completion = client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
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
            retryable = any(kw in str(e).lower() for kw in ["timeout", "rate", "503", "502", "429"])
            raise LLMError(str(e), retryable=retryable)