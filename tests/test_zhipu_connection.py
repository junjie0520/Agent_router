# tests/test_zhipu_connection.py

"""
智谱 API 连通性测试
"""

import sys
import os
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.core.adapters.zhipu_adapter import ZhipuAdapter

API_KEY = "168f20af9ecd4b548ada54e42f7ca3f9.nR6T6keG5r7ZkKv7"


@pytest.fixture(scope="module")
def adapter():
    """创建适配器实例（模块级别复用）"""
    return ZhipuAdapter(api_key=API_KEY)


def test_basic_chat(adapter):
    """测试基本对话"""
    print(f"\n📡 模型: {adapter.model_name}")
    
    response = adapter.chat(
        messages=[{"role": "user", "content": "你好，请用一句话介绍自己"}],
        max_tokens=50,
        temperature=0.1,
    )
    
    assert response.content, "回复内容不应为空"
    assert response.tokens_used > 0, "Token 使用量应大于 0"
    assert response.latency_ms > 0, "延迟应大于 0"
    assert response.finish_reason == "stop", "应正常结束"
    
    print(f"✅ 回复: {response.content}")
    print(f"⏱️ 延迟: {response.latency_ms:.0f}ms | Tokens: {response.tokens_used}")


def test_json_output(adapter):
    """测试 JSON 格式输出"""
    response = adapter.chat(
        messages=[
            {"role": "system", "content": "只输出JSON，不要加任何其他内容"},
            {"role": "user", "content": '输出: {"name": "test", "value": 123}'}
        ],
        max_tokens=100,
        temperature=0,
    )
    
    assert response.content, "回复内容不应为空"
    print(f"📝 原始回复: {response.content}")
    
    # LLMAnalyzer 的容错逻辑：提取 JSON（即使被 markdown 包裹）
    import re
    json_match = re.search(r'\{[^}]+\}', response.content, re.DOTALL)
    if json_match:
        data = json.loads(json_match.group())
        assert "name" in data
        print(f"✅ 解析成功: {data}")


def test_analyzer_format(adapter):
    """测试 LLM Analyzer 需要的分析格式"""
    system_prompt = """你是一个文本分析专家。请严格按以下 JSON 格式输出：
{
    "complexity": <1-7>,
    "privacy_level": "<none/low/medium/high/critical>",
    "has_code": <true/false>,
    "reasoning": "<简短分析>"
}"""
    
    response = adapter.chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "用户请求：用Python写一个冒泡排序函数"}
        ],
        max_tokens=200,
        temperature=0.1,
    )
    
    print(f"📝 分析结果: {response.content}")
    
    # 验证 JSON 可解析
    import re
    json_match = re.search(r'\{[^}]+\}', response.content, re.DOTALL)
    assert json_match, "应包含 JSON"
    
    data = json.loads(json_match.group())
    assert "complexity" in data
    assert "privacy_level" in data
    assert "has_code" in data
    assert "reasoning" in data
    
    print(f"✅ 复杂度: {data['complexity']}, 隐私: {data['privacy_level']}, 代码: {data['has_code']}")
    print(f"💡 推理: {data['reasoning']}")