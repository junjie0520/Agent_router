"""
规则引擎
根据复杂度 + 隐私等级 + 策略 → 查表选模型
0毫秒，100%准确
"""
from typing import List, Dict, Any, Optional


class RuleEngine:
    """规则引擎：查表选模型"""

    def select(
        self,
        complexity: float,
        privacy_level: str,
        has_code: bool,
        policy: str,
        candidates: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        返回 {"model_id": str, "reason": str}
        model_id 为空字符串表示阻断
        """
        # ============================================================
        # 1. 隐私硬约束
        # ============================================================
        if privacy_level == "critical":
            # 只允许本地模型
            safe = [c for c in candidates if c.get("is_local")]
            if not safe:
                return {"model_id": "", "reason": "CRITICAL隐私等级：检测到凭证/密钥，无可用本地私有模型"}
            candidates = safe

        elif privacy_level in ("high", "medium"):
            # 只允许本地或TEE
            safe = [c for c in candidates if c.get("is_local") or c.get("tee_enabled")]
            if not safe:
                return {"model_id": "", "reason": f"{privacy_level.upper()}隐私等级：检测到敏感信息，无可用安全模型"}
            candidates = safe

        if not candidates:
            return {"model_id": "", "reason": "所有候选模型被隐私策略过滤"}

        # ============================================================
        # 2. 能力约束
        # ============================================================
        needs_code = has_code or complexity >= 5
        if needs_code:
            code_models = [c for c in candidates if "code" in c.get("capabilities", [])]
            if code_models:
                candidates = code_models

        if not candidates:
            return {"model_id": "", "reason": "任务需要代码能力，但无可用模型"}

        # ============================================================
        # 3. 策略路由
        # ============================================================
        if policy == "cost_first":
            best = min(candidates, key=lambda c: c.get("cost_per_1k_tokens", 99))
            reason = "成本优先：选择最便宜"

        elif policy == "quality_first":
            best = max(candidates, key=lambda c: c.get("capability_score", 0))
            reason = "质量优先：选择能力最强"

        elif policy == "privacy_strict":
            safe = [c for c in candidates if c.get("is_local") or c.get("tee_enabled")]
            if safe:
                best = max(safe, key=lambda c: c.get("capability_score", 0))
                reason = "隐私严格：选择安全模型中能力最强"
            else:
                return {"model_id": "", "reason": "隐私严格策略：无安全模型可用"}

        else:  # balanced
            if needs_code or complexity >= 7:
                best = max(candidates, key=lambda c: c.get("capability_score", 0))
                reason = "均衡策略：复杂任务选择能力最强"
            else:
                best = min(candidates, key=lambda c: c.get("cost_per_1k_tokens", 99))
                reason = "均衡策略：简单任务选择最便宜"

        return {
            "model_id": best.get("id", best.get("model_id", "")),
            "reason": reason,
        }