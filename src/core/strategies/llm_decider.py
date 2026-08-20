"""
LLM 决策器
串联 PromptBuilder + LLMAdapter，解析 LLM 响应，产出 RouteReceipt
"""
import json
import time
import re
from typing import List, Dict, Any, Optional
from src.core.schemas.task import TaskFeatures, TaskType, PrivacyLevel
from src.core.schemas.receipt import (
    RouteReceipt, DecisionReason, ModelCandidate, CostBreakdown,
)
from src.core.schemas.request import RoutingPolicy
from src.core.strategies.prompt_builder import PromptBuilder
from src.core.adapters.llm_adapter import BaseLLMAdapter, LLMResponse, LLMError


def _get_candidate_id(c: Dict[str, Any], fallback: str = "") -> str:
    """安全获取候选模型 ID，兼容 id 和 model_id 两种字段名"""
    return c.get("id") or c.get("model_id") or fallback


def _get_candidate_cost_per_1k(c: Dict[str, Any]) -> float:
    """安全获取每千 token 成本"""
    cost = c.get("cost_per_1k_tokens")
    if cost is not None:
        return float(cost)
    cost_per_token = c.get("cost_per_token")
    if cost_per_token is not None:
        return float(cost_per_token) * 1000
    return 0.0


class LLMDecider:
    """
    LLM 决策器
    """

    JSON_PATTERN = re.compile(r'```(?:json)?\s*([\s\S]*?)\s*```')

    def __init__(
        self,
        llm_adapter: BaseLLMAdapter,
        prompt_builder: Optional[PromptBuilder] = None,
        max_retries: int = 1,
    ):
        self.llm = llm_adapter
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.max_retries = max_retries
        self.total_calls = 0
        self.fallback_count = 0

    # ================================================================
    # 主入口
    # ================================================================

    def decide(
        self,
        features: TaskFeatures,
        candidates: List[Dict[str, Any]],
        policy: str = "balanced",
        budget: Optional[Dict[str, Any]] = None,
        request_id: str = "",
        trace_id: str = "",
    ) -> RouteReceipt:
        start_time = time.time()
        messages = self.prompt_builder.build(features, candidates, policy, budget)
        decision_json, llm_response, retries = self._call_llm_with_retry(messages, candidates)
        decision_time_ms = (time.time() - start_time) * 1000

        return self._build_receipt(
            features=features,
            decision_json=decision_json,
            candidates=candidates,
            policy=policy,
            request_id=request_id,
            trace_id=trace_id,
            decision_time_ms=decision_time_ms,
            llm_response=llm_response,
            retries=retries,
        )

    # ================================================================
    # LLM 调用 + 重试
    # ================================================================

    def _call_llm_with_retry(
        self,
        messages: List[Dict[str, str]],
        candidates: List[Dict[str, Any]],
    ) -> tuple:
        last_error = None
        last_response = None

        for attempt in range(self.max_retries + 1):
            try:
                self.total_calls += 1
                response = self.llm.chat(messages, temperature=0.1, max_tokens=500)
                last_response = response
                decision_json = self._parse_json(response.content)
                return decision_json, response, attempt
            except LLMError as e:
                last_error = e
                if not e.retryable:
                    break
            except (json.JSONDecodeError, ValueError) as e:
                last_error = e
                if attempt < self.max_retries:
                    resp_content = last_response.content if last_response else ""
                    messages.append({"role": "assistant", "content": resp_content})
                    messages.append({
                        "role": "user",
                        "content": "你的回复不是有效的JSON格式。请严格按照要求的JSON格式重新输出。只返回JSON，不要任何其他内容。"
                    })
            except Exception as e:
                last_error = e
                break

        self.fallback_count += 1
        fallback_json = self._fallback_decision(candidates, last_error)
        return fallback_json, last_response, self.max_retries

    # ================================================================
    # JSON 解析
    # ================================================================

    def _parse_json(self, content: str) -> Dict[str, Any]:
        content = content.strip()
        match = self.JSON_PATTERN.search(content)
        if match:
            return json.loads(match.group(1).strip())

        first_brace = content.find('{')
        last_brace = content.rfind('}')
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            return json.loads(content[first_brace:last_brace + 1])

        raise ValueError(f"无法从响应中提取JSON: {content[:200]}")

    # ================================================================
    # 构造 RouteReceipt
    # ================================================================

    def _build_receipt(
        self,
        features: TaskFeatures,
        decision_json: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        policy: str,
        request_id: str,
        trace_id: str,
        decision_time_ms: float,
        llm_response: Optional[LLMResponse],
        retries: int,
    ) -> RouteReceipt:

        selected_model = decision_json.get("selected_model", "")
        confidence = decision_json.get("confidence", 0.5)
        reasoning = decision_json.get("reasoning", "")
        alternative = decision_json.get("alternative", "")
        risk_assessment = decision_json.get("risk_assessment", "")

        candidate_ids = [_get_candidate_id(c) for c in candidates]

        # 清理 LLM 返回的 selected_model
        selected_model = selected_model.strip()
        selected_model = re.sub(r'\s*\(.*?\)\s*', '', selected_model).strip()
        selected_model = selected_model.rstrip('.,;:!?，。；：！？')

        # 精确匹配
        if not selected_model or selected_model not in candidate_ids:
            matched = False
            for cid in candidate_ids:
                if cid in selected_model or selected_model in cid:
                    selected_model = cid
                    matched = True
                    break
            if not matched and candidate_ids:
                selected_model = candidate_ids[0]
                reasoning = f"LLM未指定有效模型，使用兜底策略选择 {selected_model}。" + reasoning

        model_candidates = []
        for c in candidates:
            cid = _get_candidate_id(c)
            score = confidence if cid == selected_model else 0.5
            cost_per_1k = _get_candidate_cost_per_1k(c)
            estimated_cost = cost_per_1k * features.complexity.token_count / 1000
            estimated_latency = c.get("latency_ms", 0)

            reason = None
            if cid == selected_model:
                reason = reasoning
            elif cid == alternative:
                reason = f"备选模型: {risk_assessment}" if risk_assessment else "备选模型"

            model_candidates.append(ModelCandidate(
                model_id=cid,
                score=score,
                estimated_cost=round(estimated_cost, 6),
                estimated_latency_ms=estimated_latency,
                is_available=True,
                selection_reason=reason,
            ))

        selected_cost = 0.0
        for mc in model_candidates:
            if mc.model_id == selected_model:
                selected_cost = mc.estimated_cost
                break

        requires_tee = (
            features.sensitive.has_credentials or
            features.privacy_level == PrivacyLevel.CRITICAL
        )

        # pii_detected 合并 PII + 凭证 + 内部配置
        pii_detected = []
        if features.sensitive.has_pii:
            pii_detected.extend(features.sensitive.pii_types)
        if features.sensitive.has_credentials:
            pii_detected.append("credentials")
        if features.sensitive.has_internal_config:
            pii_detected.append("internal_config")

        privacy_checks_passed = True

        selected_is_local = False
        selected_has_tee = False
        for c in candidates:
            if _get_candidate_id(c) == selected_model:
                selected_is_local = c.get("is_local", False)
                selected_has_tee = c.get("tee_enabled", False)
                break

        if features.privacy_level in (PrivacyLevel.MEDIUM, PrivacyLevel.HIGH, PrivacyLevel.CRITICAL):
            if not (selected_is_local or selected_has_tee):
                privacy_checks_passed = False

        selected_latency = 0
        for c in candidates:
            if _get_candidate_id(c) == selected_model:
                selected_latency = c.get("latency_ms", 0)
                break

        policy_values = [p.value for p in RoutingPolicy]
        if policy in policy_values:
            req_policy = RoutingPolicy(policy)
        else:
            req_policy = RoutingPolicy.BALANCED

        receipt = RouteReceipt(
            request_id=request_id,
            trace_id=trace_id,
            requested_policy=req_policy,
            effective_policy=req_policy,
            selected_model=selected_model,
            decision_reason=DecisionReason.LLM_DECIDED,
            decision_explanation=reasoning,
            candidate_models=model_candidates,
            trigger_rules=[],
            rule_chain=[],
            task_type=features.task_type,
            privacy_level=features.privacy_level,
            complexity_score=features.complexity_score,
            features_snapshot=features.to_rule_input(),
            requires_tee=requires_tee,
            pii_detected=pii_detected,
            privacy_checks_passed=privacy_checks_passed,
            estimated_cost=CostBreakdown(
                input_tokens=features.complexity.token_count,
                output_tokens=max(int(features.complexity.token_count * 0.5), 1),
                input_cost=round(selected_cost * 0.6, 6),
                output_cost=round(selected_cost * 0.4, 6),
                total_cost=round(selected_cost, 6),
            ),
            estimated_latency_ms=float(selected_latency),
            routing_latency_ms=decision_time_ms,
            extra={
                "llm_model": self.llm.model_name,
                "llm_tokens_used": llm_response.tokens_used if llm_response else 0,
                "llm_latency_ms": llm_response.latency_ms if llm_response else 0,
                "llm_retries": retries,
                "llm_confidence": confidence,
                "llm_alternative": alternative,
                "llm_risk_assessment": risk_assessment,
                "llm_raw_response": llm_response.content if llm_response else None,
                "is_fallback": retries >= self.max_retries and "兜底" in reasoning,
            },
        )

        return receipt

    # ================================================================
    # 兜底策略
    # ================================================================

    def _fallback_decision(
        self,
        candidates: List[Dict[str, Any]],
        error: Any = None,
    ) -> Dict[str, Any]:
        error_msg = str(error) if error else "未知错误"

        if not candidates:
            return {
                "selected_model": "",
                "confidence": 0.0,
                "reasoning": f"LLM决策失败且无候选模型。错误: {error_msg}",
                "alternative": None,
                "risk_assessment": "高风险 - 使用了兜底策略",
            }

        first_id = _get_candidate_id(candidates[0], "unknown")
        return {
            "selected_model": first_id,
            "confidence": 0.0,
            "reasoning": f"LLM决策失败，使用兜底策略选择第一个候选模型 {first_id}。错误: {error_msg}",
            "alternative": None,
            "risk_assessment": "高风险 - LLM决策失败，使用了兜底策略",
        }