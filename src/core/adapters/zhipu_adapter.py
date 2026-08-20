# src/core/adapters/zhipu_adapter.py

"""
智谱 AI (GLM) 适配器
基于 OpenAI 兼容接口，继承 OpenAIAdapter
"""

from typing import Optional
from src.core.adapters.llm_adapter import OpenAIAdapter


class ZhipuAdapter(OpenAIAdapter):
    """
    智谱 AI API 适配器
    
    智谱 API 完全兼容 OpenAI 的接口格式，直接继承 OpenAIAdapter，
    只需预设 base_url 和默认模型即可。
    
    用法:
        adapter = ZhipuAdapter(api_key="your-key")
        response = adapter.chat(messages=[{"role": "user", "content": "你好"}])
    """
    
    # 智谱默认配置
    DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
    DEFAULT_MODEL = "glm-4-flash"
    
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
    ):
        """
        初始化智谱适配器
        
        Args:
            api_key: 智谱 API Key（从 https://open.bigmodel.cn 获取）
            model: 模型名称，可选:
                   - glm-4-flash (默认，免费)
                   - glm-4
                   - glm-4-plus
                   - glm-4-air
                   - glm-4-long
            base_url: API 基础URL，默认智谱官方地址
            timeout: 请求超时时间（秒）
        
        Example:
            >>> adapter = ZhipuAdapter(api_key="your-api-key")
            >>> response = adapter.chat(
            ...     messages=[{"role": "user", "content": "你好"}],
            ...     max_tokens=100
            ... )
            >>> print(response.content)
            你好！有什么可以帮助你的吗？
        """
        super().__init__(
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout=timeout,
        )