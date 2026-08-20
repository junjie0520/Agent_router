"""
复杂度分析器
基于统计指标和代码特征，计算任务综合复杂度评分
支持 rule 后端（纯规则加权），预留 LLM 后端接口
"""
from typing import Optional, List
from src.core.schemas.task import (
    ComplexityMetrics, ComplexityResult, CodeFeatures,
)


class ComplexityAnalyzer:
    """
    复杂度分析器

    rule 模式：基于统计指标加权计算，确定性输出
    LLM 模式：调用 LLM 做综合评估（预留）
    """

    FACTOR_CAPS = {
        'token_count': 8000,
        'message_count': 10,
        'vocabulary_diversity': 1.0,
        'code_lines': 200,
        'code_blocks': 5,
        'languages': 3,
        'has_imports': 1,
        'has_functions': 1,
        'has_classes': 1,
        'has_multiple_files': 1,
    }

    FACTOR_WEIGHTS = {
        'token_count': 3.0,
        'message_count': 1.5,
        'vocabulary_diversity': 1.0,
        'code_lines': 2.0,
        'code_blocks': 1.0,
        'languages': 0.5,
        'has_imports': 0.3,
        'has_functions': 0.5,
        'has_classes': 0.5,
        'has_multiple_files': 0.7,
        'code_intent': 2.5,       # 有代码意图但无代码块时的基础分
        'code_generation': 3.0,   # 代码生成任务额外分
        'code_refactor': 4.0,     # 代码重构任务额外分
    }

    def analyze(
        self,
        metrics: ComplexityMetrics,
        code_features: Optional[CodeFeatures] = None,
        task_type_hint: Optional[str] = None,
        mode: str = "rule",
    ) -> ComplexityResult:
        if mode == "rule":
            return self._rule_analyze(metrics, code_features, task_type_hint)
        else:
            return self._rule_analyze(metrics, code_features, task_type_hint)

    def _rule_analyze(
        self,
        metrics: ComplexityMetrics,
        code_features: Optional[CodeFeatures] = None,
        task_type_hint: Optional[str] = None,
    ) -> ComplexityResult:
        factors = {}
        details = []

        # 1. token 数量因子
        token_factor = self._normalize(metrics.token_count, self.FACTOR_CAPS['token_count'])
        factors['token_count'] = round(token_factor * self.FACTOR_WEIGHTS['token_count'], 1)
        if metrics.token_count > 4000:
            details.append(f"长文本({metrics.token_count} tokens)")
        elif metrics.token_count > 1000:
            details.append(f"中等文本({metrics.token_count} tokens)")

        # 2. 消息轮次因子
        msg_factor = self._normalize(metrics.message_count, self.FACTOR_CAPS['message_count'])
        factors['message_rounds'] = round(msg_factor * self.FACTOR_WEIGHTS['message_count'], 1)
        if metrics.message_count > 5:
            details.append(f"多轮对话({metrics.message_count}轮)")

        # 3. 词汇多样性因子
        diversity = metrics.vocabulary_diversity
        div_factor = self._normalize(diversity, self.FACTOR_CAPS['vocabulary_diversity'])
        factors['vocabulary_diversity'] = round(div_factor * self.FACTOR_WEIGHTS['vocabulary_diversity'], 1)
        if diversity > 0.7:
            details.append(f"词汇丰富(多样性{diversity:.2f})")

        # 4. 代码相关因子
        has_code_blocks = code_features and code_features.has_code
        is_code_task = task_type_hint in ("code_gen", "code_refactor")

        if has_code_blocks:
            factors['code_lines'] = round(
                self._normalize(code_features.total_code_lines, self.FACTOR_CAPS['code_lines'])
                * self.FACTOR_WEIGHTS['code_lines'], 1
            )
            factors['code_blocks'] = round(
                self._normalize(code_features.code_block_count, self.FACTOR_CAPS['code_blocks'])
                * self.FACTOR_WEIGHTS['code_blocks'], 1
            )
            factors['languages'] = round(
                self._normalize(len(code_features.code_languages), self.FACTOR_CAPS['languages'])
                * self.FACTOR_WEIGHTS['languages'], 1
            )

            if code_features.has_imports:
                factors['has_imports'] = self.FACTOR_WEIGHTS['has_imports']
            if code_features.has_functions:
                factors['has_functions'] = self.FACTOR_WEIGHTS['has_functions']
            if code_features.has_classes:
                factors['has_classes'] = self.FACTOR_WEIGHTS['has_classes']
            if code_features.has_multiple_files:
                factors['has_multiple_files'] = self.FACTOR_WEIGHTS['has_multiple_files']

            code_parts = []
            if code_features.total_code_lines > 50:
                code_parts.append(f"{code_features.total_code_lines}行代码")
            if code_features.code_block_count > 1:
                code_parts.append(f"{code_features.code_block_count}个代码块")
            if len(code_features.code_languages) > 1:
                code_parts.append(f"多语言({', '.join(code_features.code_languages)})")
            if code_features.has_multiple_files:
                code_parts.append("多文件")
            if code_parts:
                details.append("代码任务: " + ", ".join(code_parts))
            else:
                details.append("包含代码")

        elif is_code_task:
            # 有代码意图但没有代码块
            factors['code_intent'] = self.FACTOR_WEIGHTS['code_intent']
            if task_type_hint == "code_refactor":
                factors['code_refactor'] = self.FACTOR_WEIGHTS['code_refactor']
            else:
                factors['code_generation'] = self.FACTOR_WEIGHTS['code_generation']
            details.append("代码生成任务")

        # 汇总
        total_score = sum(factors.values())
        total_score = min(total_score, 10.0)
        total_score = round(total_score, 1)

        reasoning = self._build_reasoning(total_score, details)

        return ComplexityResult(
            score=total_score,
            factors=factors,
            reasoning=reasoning,
        )

    @staticmethod
    def _normalize(value: float, cap: float) -> float:
        if cap <= 0:
            return 0.0
        return min(value / cap, 1.0)

    @staticmethod
    def _build_reasoning(score: float, details: List[str]) -> str:
        if score < 2.0:
            level = "极低复杂度"
        elif score < 4.0:
            level = "低复杂度"
        elif score < 6.0:
            level = "中等复杂度"
        elif score < 8.0:
            level = "高复杂度"
        else:
            level = "极高复杂度"

        if details:
            return f"{level}（{'; '.join(details)}）"
        return f"{level}"