"""
路由决策中枢 - 新架构版
LLMAnalyzer 分析 + RuleEngine 决策
"""
import time
import logging
from typing import List, Dict, Any, Optional

from src.core.schemas.request import RouterRequest, RoutingPolicy
from src.core.schemas.task import TaskFeatures, PrivacyLevel
from src.core.schemas.receipt import RouteReceipt, DecisionReason, CostBreakdown, ModelCandidate
from src.utils.validators import RoutingValidator
from src.core.features.llm_analyzer import LLMAnalyzer, TaskAnalysis
from src.core.router.rule_engine import RuleEngine

logger = logging.getLogger(__name__)


class DecisionError(Exception):
    def __init__(self, message: str, reason: str = "unknown"):
        super().__init__(message)
        self.reason = reason


class DecisionMaker:
    """
    新架构决策中枢
    流程：LLMAnalyzer → RuleEngine → RouteReceipt
    """

    def __init__(
        self,
        llm_analyzer: LLMAnalyzer,
        rule_engine: RuleEngine,
        model_registry: Dict[str, Any],
        validator: Optional[RoutingValidator] = None,
    ):
        self.llm_analyzer = llm_analyzer
        self.rule_engine = rule_engine
        self.model_registry = model_registry
        self.validator = validator or RoutingValidator()

        self.total_decisions = 0
        self.llm_success = 0
        self.rule_decisions = 0
        self.fallback_decisions = 0
        self.blocked_decisions = 0

    def decide(
        self,
        request: RouterRequest,
        features: TaskFeatures,
        candidates: Optional[List[Dict[str, Any]]] = None,
    ) -> RouteReceipt:
        start_time = time.time()
        self.total_decisions += 1

        # 1. 获取候选模型
        if candidates is None:
            candidates = self._load_candidates(request)
        if not candidates:
            raise DecisionError("候选模型列表为空", reason="no_candidates")

        # 2. LLM 分析（失败自动 fallback 到规则）
        messages = [{"role": m.role.value, "content": m.content} for m in request.messages]
        print(f"[DECISION] full_text={request.get_full_text()[:100]}")
        analysis = self.llm_analyzer.analyze(messages)
        if analysis.raw_response == "FALLBACK":
            self.rule_decisions += 1
        else:
            self.llm_success += 1

        # 3. 规则选模型
        result = self.rule_engine.select(
            complexity=analysis.complexity,
            privacy_level=analysis.privacy_level,
            has_code=analysis.has_code,
            policy=request.policy.value,
            candidates=candidates,
        )
        selected_model = result["model_id"]
        rule_reason = result["reason"]

        # 4. 判断是否阻断
        if not selected_model:
            self.blocked_decisions += 1
            return self._build_blocked_receipt(
                request, features, analysis, rule_reason
            )

        # 5. 构建候选列表 + 成本估算
        selected = None
        model_candidates = []
        for c in candidates:
            cid = c.get("id", c.get("model_id", ""))
            cost = c.get("cost_per_1k_tokens", 0) * features.complexity.token_count / 1000
            mc = ModelCandidate(
                model_id=cid,
                score=c.get("capability_score", 0.5),
                estimated_cost=round(cost, 6),
                estimated_latency_ms=c.get("latency_ms", 0),
                is_available=True,
                selection_reason=rule_reason if cid == selected_model else None,
            )
            model_candidates.append(mc)
            if cid == selected_model:
                selected = c

        # 6. 隐私校验
        privacy_ok = True
        if analysis.privacy_level in ("medium", "high", "critical"):
            is_safe = selected.get("is_local") or selected.get("tee_enabled")
            if not is_safe:
                privacy_ok = False

        # 7. 构建 receipt
        cost_per_1k = selected.get("cost_per_1k_tokens", 0) if selected else 0
        token_count = features.complexity.token_count
        estimated_cost = cost_per_1k * token_count / 1000

        receipt = RouteReceipt(
            request_id=request.request_id,
            trace_id=request.trace_id or request.request_id,
            requested_policy=request.policy,
            effective_policy=request.policy,
            selected_model=selected_model,
            decision_reason=DecisionReason.RULE_MATCHED,
            decision_explanation=analysis.reasoning or rule_reason,
            candidate_models=model_candidates,
            task_type=features.task_type,
            privacy_level=PrivacyLevel(analysis.privacy_level) if analysis.privacy_level != "none" else PrivacyLevel.NONE,
            complexity_score=analysis.complexity,
            features_snapshot={
                "token_count": features.complexity.token_count,
                "message_count": features.complexity.message_count,
                "complexity_score": analysis.complexity,
                "has_code": analysis.has_code,
                "privacy_level": analysis.privacy_level,
                "pii_types": analysis.pii_types,
            },
            estimated_cost=CostBreakdown(
                input_tokens=token_count,
                output_tokens=max(int(token_count * 0.5), 1),
                input_cost=round(estimated_cost * 0.6, 6),
                output_cost=round(estimated_cost * 0.4, 6),
                total_cost=round(estimated_cost, 6),
            ),
            estimated_latency_ms=selected.get("latency_ms", 0) if selected else 0,
            requires_tee=analysis.privacy_level in ("medium", "high", "critical"),
            pii_detected=analysis.pii_types,
            privacy_checks_passed=privacy_ok,
            extra={
                "llm_analysis": {
                    "complexity": analysis.complexity,
                    "privacy_level": analysis.privacy_level,
                    "has_code": analysis.has_code,
                    "reasoning": analysis.reasoning,
                    "source": "llm" if analysis.raw_response != "FALLBACK" else "rules",
                },
                "rule_engine": {"reason": rule_reason},
            },
        )

        decision_time_ms = (time.time() - start_time) * 1000
        receipt.extra["decision_time_ms"] = round(decision_time_ms, 2)

        return receipt

    def _load_candidates(self, request: RouterRequest) -> List[Dict[str, Any]]:
        if not self.model_registry:
            return []
        models = self.model_registry.get("models", [])
        candidates = []
        for m in models:
            candidates.append({
                "id": m.get("id", ""),
                "model_id": m.get("id", ""),
                "name": m.get("name", ""),
                "cost_per_1k_tokens": m.get("pricing", {}).get("input_per_1k", 0),
                "latency_ms": m.get("latency_ms", 0),
                "capability_score": m.get("capability_score", 0.5),
                "capabilities": m.get("capabilities", []),
                "is_local": m.get("is_local", False),
                "tee_enabled": m.get("tee_enabled", False),
            })
        if request.budget and request.budget.blocked_models:
            blocked = set(request.budget.blocked_models)
            candidates = [c for c in candidates if c["id"] not in blocked]
        if request.budget and request.budget.preferred_models:
            preferred = set(request.budget.preferred_models)
            preferred_candidates = [c for c in candidates if c["id"] in preferred]
            if preferred_candidates:
                candidates = preferred_candidates
        return candidates

    def _build_blocked_receipt(
        self,
        request: RouterRequest,
        features: TaskFeatures,
        analysis: TaskAnalysis,
        reason: str,
    ) -> RouteReceipt:
        return RouteReceipt(
            request_id=request.request_id,
            trace_id=request.trace_id or request.request_id,
            requested_policy=request.policy,
            effective_policy=request.policy,
            selected_model="",
            decision_reason=DecisionReason.PRIVACY_ENFORCEMENT,
            decision_explanation=f"路由被阻断: {reason}",
            task_type=features.task_type,
            privacy_level=PrivacyLevel(analysis.privacy_level) if analysis.privacy_level != "none" else PrivacyLevel.NONE,
            complexity_score=analysis.complexity,
            features_snapshot={
                "complexity_score": analysis.complexity,
                "privacy_level": analysis.privacy_level,
                "pii_types": analysis.pii_types,
            },
            estimated_cost=CostBreakdown(),
            estimated_latency_ms=0,
            requires_tee=True,
            pii_detected=analysis.pii_types,
            privacy_checks_passed=False,
            errors=[reason],
            extra={
                "llm_analysis": {
                    "complexity": analysis.complexity,
                    "privacy_level": analysis.privacy_level,
                    "reasoning": analysis.reasoning,
                }
            },
        )

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_decisions": self.total_decisions,
            "llm_success": self.llm_success,
            "rule_decisions": self.rule_decisions,
            "fallback_decisions": self.fallback_decisions,
            "blocked_decisions": self.blocked_decisions,
        }