"""
Prompt 构建器
将 TaskFeatures + 候选模型 + 策略 转换为 LLM 可理解的决策 Prompt
"""
from typing import List, Dict, Any, Optional
from src.core.schemas.task import TaskFeatures, TaskType, PrivacyLevel
from src.core.schemas.request import RoutingPolicy


class PromptBuilder:

    DEFAULT_SYSTEM_PROMPTS = {
        "cost_first": """你是路由决策器，要以低成本优先。规则：
1.出现中等及以上泄露隐私的风险无视复杂度选mock-tee
2.任务复杂或者复杂度>6 选mock-strong
3.中等或简单任务 → 选 mock-cheap
只返回JSON。""",

        "quality_first": """你是路由决策器，以处理能力优先。规则：
1.出现中等及以上泄露隐私的风险无视复杂度选mock-tee
2.中等或复杂任务或复杂度>4 → 选 mock-strong
3.简单任务 → 选 mock-cheap
只返回JSON。""",

        "privacy_strict": """你是路由决策器，如果有敏感数据，无视复杂度必须使用安全模型。规则：
1. 只要泄露隐私或者风险大于等于中级 → 必须选mock-tee
2. 安全任务时，复杂或者复杂度>6 选mock-strong
3. 安全任务时，中等或简单任务 → 选 mock-cheap
只返回JSON。""",

        "balanced": """你是路由决策器。规则：
1.出现明显泄露隐私 选mock-tee
2. 任务复杂或者复杂度>6 选mock-strong
3. 中等或简单任务 → 选 mock-cheap
只返回JSON。""",
    }

    OUTPUT_FORMAT = """
返回格式：
```json
{"selected_model":"模型ID","confidence":0.9,"reasoning":"理由","alternative":null,"risk_assessment":"低风险"}
```"""

    def __init__(self, policy_templates: Optional[Dict[str, str]] = None):
        self._system_prompts = {**self.DEFAULT_SYSTEM_PROMPTS}
        if policy_templates:
            self._system_prompts.update(policy_templates)

    def build(
        self,
        features: TaskFeatures,
        candidates: List[Dict[str, Any]],
        policy: str = "balanced",
        budget: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, str]]:
        system_prompt = self._build_system_prompt(policy)
        user_prompt = self._build_user_prompt(features, candidates, policy, budget)
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _build_system_prompt(self, policy: str) -> str:
        base = self._system_prompts.get(policy, self._system_prompts["balanced"])
        return base + self.OUTPUT_FORMAT

    def _build_user_prompt(
        self,
        features: TaskFeatures,
        candidates: List[Dict[str, Any]],
        policy: str = "balanced",
        budget: Optional[Dict[str, Any]] = None,
    ) -> str:
        parts = []
        parts.append(self._format_task_section(features))

        if features.privacy_level in (PrivacyLevel.MEDIUM, PrivacyLevel.HIGH, PrivacyLevel.CRITICAL):
            parts.append(self._format_privacy_warning(features, policy))

        parts.append(self._format_candidates_section(candidates, policy))

        if budget:
            parts.append(self._format_budget_section(budget))

        return "\n\n".join(parts)

    def _format_task_section(self, features: TaskFeatures) -> str:
        lines = ["## 任务"]
        lines.append(f"类型: {self._task_type_cn(features.task_type)}")
        lines.append(f"复杂度: {features.complexity_score}/10")
        lines.append(f"Token: {features.complexity.token_count}")
        if features.code_features.has_code:
            langs = ", ".join(features.code_features.code_languages) if features.code_features.code_languages else "未知"
            lines.append(f"代码: {langs}, {features.code_features.total_code_lines}行")
        return "\n".join(lines)

    def _format_privacy_warning(self, features: TaskFeatures, policy: str = "balanced") -> str:
        lines = ["## ⚠️ 敏感信息"]
        lines.append(f"等级: {self._privacy_level_cn(features.privacy_level)}")

        if features.sensitive.has_credentials:
            lines.append("🔴 凭证/密钥 → 只能选 mock-tee")
        elif features.sensitive.has_pii:
            pii_str = ", ".join(features.sensitive.pii_types)
            lines.append(f"🟠 PII({pii_str}) → 只能选 mock-tee")

        if policy != "privacy_strict":
            lines.append("（非privacy_strict策略也必须遵守安全红线）")

        return "\n".join(lines)

    def _format_candidates_section(self, candidates: List[Dict[str, Any]], policy: str = "balanced") -> str:
        lines = ["## 可选模型"]
        is_privacy_strict = (policy == "privacy_strict")

        # 隐私严格模式前置提示（新增，强制告知模型准入规则）
        if is_privacy_strict:
            lines.append("【重要约束】privacy_strict策略：如果有敏感数据，无视复杂度必须使用安全模型")

        for m in candidates:
            mid = m.get("id", m.get("model_id", ""))
            cost = m.get("cost_per_1k_tokens", 0)
            caps = m.get("capabilities", [])
            is_local = m.get("is_local", False)
            tee = m.get("tee_enabled", False)

            # 语义重构，不再使用模糊的“云端”
            if tee or is_local:
                safety_label = "✅ 安全"
            else:
                if is_privacy_strict:
                    safety_label = "不安全"
                else:
                    safety_label = "⚠️不安全"

            lines.append(f"- {mid}: ${cost:.4f}/1k tokens, {safety_label}, {', '.join(caps[:3])}")

        return "\n".join(lines)

    def _format_budget_section(self, budget: Any) -> str:
        lines = ["## 预算"]
        if hasattr(budget, 'max_cost_usd'):
            lines.append(f"最大成本: ${budget.max_cost_usd:.4f}")
            if budget.max_latency_ms:
                lines.append(f"最大延迟: {budget.max_latency_ms}ms")
        elif isinstance(budget, dict):
            if budget.get("max_cost_usd"):
                lines.append(f"最大成本: ${budget['max_cost_usd']:.4f}")
            if budget.get("max_latency_ms"):
                lines.append(f"最大延迟: {budget['max_latency_ms']}ms")
        return "\n".join(lines)

    @staticmethod
    def _task_type_cn(task_type: TaskType) -> str:
        mapping = {
            TaskType.SIMPLE_QA: "简单问答",
            TaskType.CODE_GENERATION: "代码生成",
            TaskType.CODE_REFACTOR: "代码重构",
            TaskType.TOOL_USE: "工具调用",
            TaskType.LONG_CONTEXT: "长上下文",
            TaskType.CREATIVE_WRITING: "创意写作",
            TaskType.DATA_ANALYSIS: "数据分析",
            TaskType.TRANSLATION: "翻译",
            TaskType.SUMMARIZATION: "摘要",
            TaskType.SENSITIVE_HANDLING: "敏感数据",
            TaskType.UNKNOWN: "未知",
        }
        return mapping.get(task_type, task_type.value)

    @staticmethod
    def _privacy_level_cn(level: PrivacyLevel) -> str:
        mapping = {
            PrivacyLevel.NONE: "无",
            PrivacyLevel.LOW: "低",
            PrivacyLevel.MEDIUM: "中",
            PrivacyLevel.HIGH: "高",
            PrivacyLevel.CRITICAL: "极高",
        }
        return mapping.get(level, level.value)