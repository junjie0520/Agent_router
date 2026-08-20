"""测试 LLMAnalyzer"""
import sys
from pathlib import Path

# 修正：项目根目录加入搜索路径（原代码只加到 tests 目录，找不到 src）
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.features.llm_analyzer import LLMAnalyzer
from src.extensions.local_adapter import OllamaAdapter


def test_llm_analyzer_cases():
    analyzer = LLMAnalyzer(OllamaAdapter(model="phi3:latest"))

    tests = [
        "你好，今天天气怎么样",
        "用Python写一个冒泡排序函数",
        "我的身份证号是110101199001011234，帮我查下归属地",
        "我的AWS AccessKey是AKIA1234567890ABCDEF，SecretKey是wJalrXUtnFEMI",
    ]

    for text in tests:
        result = analyzer.analyze(text)
        print(f"输入: {text[:40]}...")
        print(f"  复杂度: {result.complexity}, 隐私: {result.privacy_level}, 代码: {result.has_code}")
        print(f"  理由: {result.reasoning}")
        print(f"  PII: {result.pii_types}")
        print()

        # 基础断言，保证结果字段合法
        assert 0 <= result.complexity <= 10
        assert result.privacy_level in ("none", "low", "medium", "high", "critical")
        assert isinstance(result.pii_types, list)