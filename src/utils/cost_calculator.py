"""
成本计算器
统一的成本估算工具，供 engine、llm_decider、规则引擎复用
"""
from typing import Dict, Any, Optional
from src.core.schemas.receipt import CostBreakdown


class CostCalculator:
    """成本计算器"""

    def __init__(self, input_output_ratio: float = 0.6):
        """
        Args:
            input_output_ratio: 输入 token 占比，默认 0.6（即 60% 输入，40% 输出）
        """
        self.input_ratio = input_output_ratio

    def estimate(
        self,
        total_tokens: int,
        cost_per_1k_input: float = 0.0,
        cost_per_1k_output: float = 0.0,
    ) -> CostBreakdown:
        """
        基于总 token 数估算成本

        Args:
            total_tokens: 预估的总 token 数
            cost_per_1k_input: 每千输入 token 成本
            cost_per_1k_output: 每千输出 token 成本

        Returns:
            CostBreakdown: 成本明细
        """
        input_tokens = max(int(total_tokens * self.input_ratio), 1)
        output_tokens = max(total_tokens - input_tokens, 1)

        input_cost = (input_tokens / 1000) * cost_per_1k_input
        output_cost = (output_tokens / 1000) * cost_per_1k_output

        return CostBreakdown(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            input_cost=round(input_cost, 6),
            output_cost=round(output_cost, 6),
            total_cost=round(input_cost + output_cost, 6),
        )

    def from_actual(
        self,
        actual_tokens: int,
        cost_per_1k_input: float = 0.0,
        cost_per_1k_output: float = 0.0,
        actual_input_ratio: Optional[float] = None,
    ) -> CostBreakdown:
        """
        根据实际 token 用量计算实际成本

        Args:
            actual_tokens: 实际使用的 token 数
            cost_per_1k_input: 每千输入 token 成本
            cost_per_1k_output: 每千输出 token 成本
            actual_input_ratio: 实际输入占比，None 则使用默认值

        Returns:
            CostBreakdown: 成本明细
        """
        ratio = actual_input_ratio if actual_input_ratio is not None else self.input_ratio
        input_tokens = max(int(actual_tokens * ratio), 1)
        output_tokens = max(actual_tokens - input_tokens, 1)

        input_cost = (input_tokens / 1000) * cost_per_1k_input
        output_cost = (output_tokens / 1000) * cost_per_1k_output

        return CostBreakdown(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            input_cost=round(input_cost, 6),
            output_cost=round(output_cost, 6),
            total_cost=round(input_cost + output_cost, 6),
        )

    def rank_by_cost(
        self,
        candidates: list,
        total_tokens: int,
    ) -> list:
        """
        按成本从低到高排序候选模型

        Args:
            candidates: 候选模型列表，每个需包含 cost_per_1k_input 和 cost_per_1k_output
            total_tokens: 预估总 token 数

        Returns:
            排序后的候选模型列表，附带 estimated_cost 字段
        """
        ranked = []
        for c in candidates:
            cost_input = c.get("cost_per_1k_input", c.get("cost_per_1k_tokens", 0))
            cost_output = c.get("cost_per_1k_output", cost_input * 2)

            breakdown = self.estimate(total_tokens, cost_input, cost_output)
            ranked.append({**c, "estimated_cost": breakdown.total_cost})

        ranked.sort(key=lambda x: x["estimated_cost"])
        return ranked

    @staticmethod
    def compare(a: CostBreakdown, b: CostBreakdown) -> Dict[str, Any]:
        """
        比较两个成本明细

        Returns:
            包含差异信息的字典
        """
        return {
            "total_diff": round(a.total_cost - b.total_cost, 6),
            "input_diff": round(a.input_cost - b.input_cost, 6),
            "output_diff": round(a.output_cost - b.output_cost, 6),
            "a_cheaper": a.total_cost < b.total_cost,
            "savings_pct": round(
                (abs(a.total_cost - b.total_cost) / max(a.total_cost, b.total_cost, 0.000001)) * 100, 2
            ),
        }


# 默认实例
_default_calculator = CostCalculator()


def get_cost_calculator() -> CostCalculator:
    return _default_calculator