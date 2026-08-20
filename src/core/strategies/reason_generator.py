"""
决策理由生成器
规则做出决策后，用 LLM 把结果翻译成自然语言解释，不做模型选择。
"""
from typing import List, Optional
from src.core.adapters.llm_adapter import BaseLLMAdapter


class ReasonGenerator:
    """
    理由生成器

    只负责把决策结果翻译成可读解释，不参与选模型。
    如果 LLM 不可用或失败，自动回退到规则模板。
    """

    def __init__(self, llm_adapter: Optional[BaseLLMAdapter] = None):
        self.llm = llm_adapter

    def generate(
        self,
        selected_model: str,
        task_type: str,
        complexity_score: float,
        privacy_level: str,
        policy: str,
        pii_types: Optional[List[str]] = None,
        capabilities: Optional[List[str]] = None,
    ) -> str:
        if self.llm is None:
            return self._rule_template(
                selected_model, policy, task_type, privacy_level, complexity_score
            )

        prompt = self._build_prompt(
            selected_model, task_type, complexity_score,
            privacy_level, policy, pii_types, capabilities
        )

        try:
            response = self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=120,
            )
            return response.content.strip()
        except Exception:
            return self._rule_template(
                selected_model, policy, task_type, privacy_level, complexity_score
            )

    def _build_prompt(self, selected_model, task_type, complexity,
                      privacy, policy, pii, caps):
        pii_str = ", ".join(pii) if pii else "无"
        caps_str = ", ".join(caps) if caps else "通用"

        return f"""已知系统已选择模型：{selected_model}。

上下文：
- 策略：{policy}
- 任务类型：{task_type}
- 复杂度：{complexity}/10
- 隐私等级：{privacy}
- 检测到的 PII：{pii_str}
- 模型能力：{caps_str}

请用一句流畅的中文，向用户解释为什么选择这个模型。
不要评价模型本身，只说明决策逻辑。直接返回一句话。"""

    @staticmethod
    def _rule_template(selected_model, policy, task_type, privacy_level, complexity):
        if privacy_level in ("critical", "high", "medium"):
            return (
                f"基于{policy}策略，检测到敏感信息（隐私等级：{privacy_level}），"
                f"已自动选择具备安全能力的{selected_model}模型以确保数据安全。"
            )
        if task_type in ("code_gen", "code_refactor"):
            return (
                f"检测到代码任务（复杂度：{complexity}/10），"
                f"根据{policy}策略选择具备代码能力的{selected_model}模型。"
            )
        return (
            f"基于{policy}策略，综合任务类型（{task_type}）和复杂度（{complexity}/10），"
            f"选择{selected_model}模型。"
        )