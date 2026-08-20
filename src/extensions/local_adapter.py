"""
Ollama 本地模型适配器
"""
import time
import json
import urllib.request
import urllib.error
from typing import List, Dict, Any, Optional

from src.core.adapters.llm_adapter import BaseLLMAdapter, LLMResponse, LLMError


class OllamaAdapter(BaseLLMAdapter):

    def __init__(
        self,
        model: str = "qwen2.5:0.5b",
        base_url: str = "http://localhost:11434",
        timeout: float = 60.0,
    ):
        self._model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @property
    def model_name(self) -> str:
        return self._model

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 500,
        **kwargs
    ) -> LLMResponse:
        url = f"{self.base_url}/api/chat"
        payload = json.dumps({
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        start = time.time()

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            if "timed out" in str(e.reason).lower():
                raise LLMError(f"Ollama 请求超时", retryable=True)
            raise LLMError(f"无法连接 Ollama 服务，请确保已启动", retryable=True)
        except Exception as e:
            raise LLMError(f"Ollama 请求失败: {e}", retryable=False)

        latency = (time.time() - start) * 1000

        message = data.get("message", {})
        content = message.get("content", "")

        return LLMResponse(
            content=content,
            model=data.get("model", self._model),
            tokens_used=data.get("eval_count", 0) + data.get("prompt_eval_count", 0),
            latency_ms=latency,
            finish_reason=data.get("done_reason", "stop"),
            raw_response=data,
        )

    def list_models(self) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/api/tags"
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("models", [])
        except Exception:
            return []