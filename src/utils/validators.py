"""
Agent Router - 业务校验器

基于已定义的 Schema，实现完整的校验逻辑：
- 隐私约束校验（核心）
- 策略一致性校验
- 凭证完整性校验
- 降级链路校验
- 任务特征自洽性校验
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from src.core.schemas.request import RouterRequest, RoutingPolicy, BudgetConstraint
from src.core.schemas.task import (
    TaskFeatures, TaskType, PrivacyLevel,
    CodeFeatures, SensitiveFeatures, ToolFeatures, ComplexityMetrics
)
from src.core.schemas.receipt import (
    RouteReceipt, ModelCandidate, FallbackStep, CostBreakdown,
    DecisionReason, RuleTrigger
)


# ============================================================
# 校验报告
# ============================================================

@dataclass
class ValidationReport:
    """统一的校验报告"""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def merge(self, other: "ValidationReport") -> "ValidationReport":
        """合并另一个校验报告"""
        return ValidationReport(
            is_valid=self.is_valid and other.is_valid,
            errors=self.errors + other.errors,
            warnings=self.warnings + other.warnings,
        )

    def __repr__(self) -> str:
        status = "✅ PASS" if self.is_valid else "❌ FAIL"
        parts = [f"ValidationReport: {status}"]
        if self.errors:
            parts.append(f"  Errors ({len(self.errors)}):")
            for e in self.errors:
                parts.append(f"    - {e}")
        if self.warnings:
            parts.append(f"  Warnings ({len(self.warnings)}):")
            for w in self.warnings:
                parts.append(f"    - {w}")
        return "\n".join(parts)


# ============================================================
# 隐私合规模型注册表（硬编码，后续可迁移到 registry.yaml）
# ============================================================

# 隐私合规模型白名单：这些模型支持本地推理或 TEE，可以处理敏感数据
PRIVACY_COMPLIANT_MODELS: Dict[str, Dict[str, Any]] = {
    "local-private-llm-v1": {
        "privacy_compliant": True,
        "supports_tee": False,
        "is_local": True,
        "capability_score": 0.7,
    },
    "local-private-llm-v2": {
        "privacy_compliant": True,
        "supports_tee": True,
        "is_local": True,
        "capability_score": 0.85,
    },
    "tee-gpt-4": {
        "privacy_compliant": True,
        "supports_tee": True,
        "is_local": False,
        "capability_score": 0.95,
    },
    "gpt-4": {
        "privacy_compliant": False,
        "supports_tee": False,
        "is_local": False,
        "capability_score": 0.95,
    },
    "gpt-3.5-turbo": {
        "privacy_compliant": False,
        "supports_tee": False,
        "is_local": False,
        "capability_score": 0.6,
    },
    "claude-opus": {
        "privacy_compliant": False,
        "supports_tee": False,
        "is_local": False,
        "capability_score": 0.93,
    },
    "local-llama-8b": {
        "privacy_compliant": True,
        "supports_tee": False,
        "is_local": True,
        "capability_score": 0.45,
    },
}


def get_model_info(model_id: str) -> Optional[Dict[str, Any]]:
    """获取模型信息"""
    return PRIVACY_COMPLIANT_MODELS.get(model_id)


# ============================================================
# 1. 请求结构校验
# ============================================================

def validate_request_structure(request: RouterRequest) -> ValidationReport:
    """
    校验 RouterRequest 结构完整性

    检查项：
    - messages 是否为空
    - 如果有 tools，检查 function 定义是否包含 name
    - trace_id 为空时给出警告
    """
    errors = []
    warnings = []

    # messages 非空（Pydantic 已有 min_length=1，此处做业务级复验）
    if not request.messages:
        errors.append("messages 不能为空")
    else:
        # 检查是否有实际内容
        has_content = any(msg.content.strip() for msg in request.messages)
        if not has_content:
            errors.append("所有消息内容均为空字符串")

    # 检查工具定义
    if request.has_tools():
        for i, tool in enumerate(request.tools):
            func = tool.function
            if "name" not in func:
                errors.append(f"tool[{i}] 缺少 function.name")
            if "parameters" not in func:
                errors.append(f"tool[{i}] 缺少 function.parameters")

    # trace_id 检查
    if not request.trace_id:
        warnings.append("trace_id 未设置，将自动生成")

    # 预算约束检查
    if request.budget:
        if request.budget.max_cost_usd is not None and request.budget.max_cost_usd <= 0:
            errors.append("max_cost_usd 必须大于 0")
        if request.budget.max_latency_ms is not None and request.budget.max_latency_ms <= 0:
            errors.append("max_latency_ms 必须大于 0")

    return ValidationReport(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


# ============================================================
# 2. 任务特征自洽性校验
# ============================================================

def validate_task_features(features: TaskFeatures) -> ValidationReport:
    """
    校验 TaskFeatures 内部一致性

    检查项：
    - task_type 与 code_features 是否匹配
    - privacy_level 与 sensitive 是否匹配
    - complexity_score 范围
    """
    errors = []
    warnings = []

    # complexity_score 范围检查（Schema 已有 0-10 约束，此处做业务确认）
    if features.complexity_score < 0 or features.complexity_score > 10:
        errors.append(f"complexity_score 越界: {features.complexity_score}")

    # task_type 与 code_features 自洽性
    code_task_types = {TaskType.CODE_GENERATION, TaskType.CODE_REFACTOR}
    if features.task_type in code_task_types and not features.code_features.has_code:
        warnings.append(
            f"task_type={features.task_type.value} 但 has_code=False，"
            f"可能特征提取有误"
        )
    if features.code_features.has_code and features.task_type not in code_task_types:
        if features.task_type != TaskType.UNKNOWN:
            warnings.append(
                f"检测到代码块但 task_type={features.task_type.value}，"
                f"建议检查分类逻辑"
            )

    # privacy_level 与 sensitive 自洽性
    high_privacy = {PrivacyLevel.HIGH, PrivacyLevel.CRITICAL}
    if features.privacy_level in high_privacy and not features.sensitive.has_pii:
        warnings.append(
            f"privacy_level={features.privacy_level.value} 但 has_pii=False，"
            f"可能隐私标签过于严格"
        )
    if features.sensitive.has_pii and features.privacy_level == PrivacyLevel.NONE:
        errors.append(
            f"检测到 PII 但 privacy_level=NONE，"
            f"这是严重的不一致，必须修复"
        )

    # risk_score 与 privacy_level 一致性
    if features.sensitive.risk_score > 0.7 and features.privacy_level not in high_privacy:
        warnings.append(
            f"risk_score={features.sensitive.risk_score} 较高，"
            f"但 privacy_level={features.privacy_level.value}"
        )

    # 工具特征与 task_type
    tool_task_types = {TaskType.TOOL_USE, TaskType.DATA_ANALYSIS}
    if features.tool_features.tool_count > 0 and features.task_type not in tool_task_types:
        if features.task_type != TaskType.UNKNOWN:
            warnings.append(
                f"包含工具定义但 task_type={features.task_type.value}"
            )

    return ValidationReport(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


# ============================================================
# 3. 隐私约束校验（核心 MVP）
# ============================================================

def validate_privacy_constraints(
    features: TaskFeatures,
    receipt: RouteReceipt,
) -> ValidationReport:
    """
    隐私约束校验 — MVP 最核心的校验逻辑

    检查项：
    - 高敏感任务是否分配了隐私合规模型
    - 有凭证/密钥时是否要求 TEE
    - receipt.privacy_checks_passed 是否与实际情况一致
    """
    errors = []
    warnings = []

    privacy_level = features.privacy_level
    selected_model = receipt.selected_model
    model_info = get_model_info(selected_model)

    # 模型不在注册表中
    if model_info is None:
        warnings.append(
            f"模型 {selected_model} 不在隐私注册表中，"
            f"无法进行隐私合规校验，假定为不合规"
        )
        model_info = {"privacy_compliant": False, "supports_tee": False}

    # 高敏感任务强制隐私合规
    if privacy_level in (PrivacyLevel.HIGH, PrivacyLevel.CRITICAL):
        if not model_info["privacy_compliant"]:
            errors.append(
                f"隐私违规: 任务隐私等级={privacy_level.value}，"
                f"但选中模型 {selected_model} 不是隐私合规模型。"
                f"敏感任务必须使用本地私有模型或 TEE 模型。"
            )

    # 凭证/密钥场景强制 TEE
    if features.sensitive.has_credentials:
        if not model_info["supports_tee"]:
            errors.append(
                f"合规违规: 任务包含凭证/密钥，"
                f"但模型 {selected_model} 不支持 TEE。"
                f"处理凭证的任务必须在可信执行环境中运行。"
            )
        if not receipt.requires_tee:
            errors.append(
                f"合规违规: 任务包含凭证/密钥，"
                f"但 receipt.requires_tee=False，必须设为 True"
            )

    # requires_tee 与实际模型能力一致性
    if receipt.requires_tee and not model_info["supports_tee"]:
        errors.append(
            f"合规违规: receipt.requires_tee=True，"
            f"但模型 {selected_model} 不支持 TEE"
        )

    # privacy_checks_passed 一致性校验
    if receipt.privacy_checks_passed and len(errors) > 0:
        errors.append(
            f"逻辑不一致: receipt.privacy_checks_passed=True，"
            f"但实际存在隐私违规: {errors[0]}"
        )

    # PII 检测结果同步
    if features.sensitive.has_pii:
        detected_types = features.sensitive.pii_types
        if set(detected_types) != set(receipt.pii_detected):
            warnings.append(
                f"PII 类型不一致: features={detected_types}, "
                f"receipt={receipt.pii_detected}"
            )

    return ValidationReport(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


# ============================================================
# 4. 策略一致性校验
# ============================================================

def validate_policy_consistency(
    request: RouterRequest,
    receipt: RouteReceipt,
) -> ValidationReport:
    """
    校验路由决策是否遵循了请求的策略

    检查项：
    - cost_first: 是否选了候选中最便宜的
    - quality_first: 是否选了候选中能力最强的
    - privacy_strict: 是否满足隐私约束
    - fixed_strong/fixed_cheap: 是否匹配预设模型
    - LLM 决策模式：豁免严格的 decision_reason 与 policy 对应关系
    """
    errors = []
    warnings = []

    policy = request.policy
    selected = receipt.selected_model
    candidates = receipt.candidate_models

    # LLM 决策模式：决策由 LLM 根据 prompt 策略做出，不强制 decision_reason 与 policy 一一对应
    is_llm_mode = receipt.decision_reason == DecisionReason.LLM_DECIDED

    if policy == RoutingPolicy.PRIVACY_STRICT:
        model_info = get_model_info(selected)
        if model_info and not model_info["privacy_compliant"]:
            errors.append(
                f"策略违规: policy=privacy_strict，"
                f"但选中模型 {selected} 不支持隐私保护"
            )
        if not is_llm_mode and receipt.decision_reason != DecisionReason.PRIVACY_ENFORCEMENT:
            warnings.append(
                f"privacy_strict 策略下 decision_reason 应为 privacy_enforced，"
                f"实际为 {receipt.decision_reason.value}"
            )

    elif policy == RoutingPolicy.COST_FIRST:
        if candidates:
            available = [c for c in candidates if c.is_available]
            if available:
                cheapest = min(available, key=lambda c: c.estimated_cost)
                if selected != cheapest.model_id:
                    warnings.append(
                        f"cost_first 策略下未选中最便宜模型: "
                        f"selected={selected}(${receipt.estimated_cost.total_cost:.4f}), "
                        f"cheapest={cheapest.model_id}(${cheapest.estimated_cost:.4f})"
                    )
        if not is_llm_mode and receipt.decision_reason != DecisionReason.BUDGET_CONSTRAINT:
            warnings.append(
                f"cost_first 策略下 decision_reason 建议为 budget_constrained，"
                f"实际为 {receipt.decision_reason.value}"
            )

    elif policy == RoutingPolicy.QUALITY_FIRST:
        if candidates:
            available = [c for c in candidates if c.is_available]
            if available:
                best = max(available, key=lambda c: c.score)
                if selected != best.model_id:
                    warnings.append(
                        f"quality_first 策略下未选中最高分模型: "
                        f"selected={selected}(score={receipt.estimated_cost.total_cost:.2f}), "
                        f"best={best.model_id}(score={best.score:.2f})"
                    )

    elif policy == RoutingPolicy.BALANCED:
        if candidates and len(candidates) > 1:
            available = [c for c in candidates if c.is_available]
            worst_of_both = min(available, key=lambda c: (c.score, -c.estimated_cost))
            if selected == worst_of_both.model_id:
                warnings.append(
                    f"balanced 策略下选中了评分最低且成本最高的模型，建议复核"
                )

    elif policy == RoutingPolicy.FIXED_STRONG:
        if candidates:
            available = [c for c in candidates if c.is_available]
            if available:
                best = max(available, key=lambda c: c.score)
                if selected != best.model_id:
                    errors.append(
                        f"fixed_strong 策略要求选最强模型 {best.model_id}，"
                        f"实际选中 {selected}"
                    )

    elif policy == RoutingPolicy.FIXED_CHEAP:
        if candidates:
            available = [c for c in candidates if c.is_available]
            if available:
                cheapest = min(available, key=lambda c: c.estimated_cost)
                if selected != cheapest.model_id:
                    errors.append(
                        f"fixed_cheap 策略要求选最便宜模型 {cheapest.model_id}，"
                        f"实际选中 {selected}"
                    )

    # 预算约束检查（所有模式通用）
    if request.budget and request.budget.max_cost_usd is not None:
        if receipt.estimated_cost.total_cost > request.budget.max_cost_usd:
            if not receipt.budget_exceeded:
                errors.append(
                    f"预算超限: 预估成本 ${receipt.estimated_cost.total_cost:.4f} > "
                    f"预算上限 ${request.budget.max_cost_usd:.4f}，"
                    f"但 budget_exceeded=False"
                )
            else:
                warnings.append(
                    f"预算超限: 预估成本 ${receipt.estimated_cost.total_cost:.4f} > "
                    f"预算上限 ${request.budget.max_cost_usd:.4f}"
                )

    if request.budget and request.budget.max_latency_ms is not None:
        if receipt.estimated_latency_ms > request.budget.max_latency_ms:
            warnings.append(
                f"延迟超限: 预估延迟 {receipt.estimated_latency_ms}ms > "
                f"延迟上限 {request.budget.max_latency_ms}ms"
            )

    return ValidationReport(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


# ============================================================
# 5. 凭证完整性校验
# ============================================================

def validate_receipt_consistency(
    receipt: RouteReceipt,
    features: TaskFeatures,
) -> ValidationReport:
    """
    校验 RouteReceipt 内部一致性及其与 TaskFeatures 的一致性

    检查项：
    - task_type / privacy_level / complexity_score 与 features 一致
    - candidate_models 包含 selected_model
    - is_fallback 与 fallback_chain 一致
    - estimated_cost 的 total = input + output
    - decision_reason 合理性
    - LLM 决策模式语义正确性
    """
    errors = []
    warnings = []

    # 与 features 的一致性
    if receipt.task_type != features.task_type:
        errors.append(
            f"task_type 不一致: receipt={receipt.task_type.value}, "
            f"features={features.task_type.value}"
        )

    if receipt.privacy_level != features.privacy_level:
        errors.append(
            f"privacy_level 不一致: receipt={receipt.privacy_level.value}, "
            f"features={features.privacy_level.value}"
        )

    # ★ 修改：complexity_score 改为从 TaskFeatures 顶层取值
    if abs(receipt.complexity_score - features.complexity_score) > 0.01:
        warnings.append(
            f"complexity_score 不一致: receipt={receipt.complexity_score}, "
            f"features={features.complexity_score}"
        )

    # candidate_models 包含 selected_model
    if receipt.candidate_models:
        candidate_ids = [c.model_id for c in receipt.candidate_models]
        if receipt.selected_model not in candidate_ids:
            errors.append(
                f"selected_model={receipt.selected_model} "
                f"不在 candidate_models 中: {candidate_ids}"
            )

    # is_fallback 与 fallback_chain 一致性
    if receipt.is_fallback and not receipt.fallback_chain:
        errors.append("is_fallback=True 但 fallback_chain 为空")
    if not receipt.is_fallback and receipt.fallback_chain:
        warnings.append("is_fallback=False 但 fallback_chain 非空")

    # 成本计算一致性
    cost = receipt.estimated_cost
    expected_total = cost.input_cost + cost.output_cost
    if abs(cost.total_cost - expected_total) > 0.001:
        errors.append(
            f"成本计算不一致: total=${cost.total_cost:.4f}, "
            f"input(${cost.input_cost:.4f}) + output(${cost.output_cost:.4f}) = ${expected_total:.4f}"
        )

    # decision_reason 与 is_fallback 一致性
    if receipt.is_fallback and receipt.decision_reason != DecisionReason.FALLBACK:
        warnings.append(
            f"is_fallback=True 但 decision_reason={receipt.decision_reason.value}"
        )

    # LLM 决策模式：trigger_rules 应为空
    if receipt.decision_reason == DecisionReason.LLM_DECIDED and receipt.trigger_rules:
        warnings.append("decision_reason=llm_decided 但 trigger_rules 非空，LLM 决策不应触发规则")

    # 规则匹配模式：trigger_rules 不应为空
    if receipt.decision_reason == DecisionReason.RULE_MATCHED and not receipt.trigger_rules:
        warnings.append("decision_reason=rule_matched 但 trigger_rules 为空")

    # rule_chain 与 trigger_rules 一致性
    if receipt.rule_chain:
        rule_ids = [r.rule_id for r in receipt.trigger_rules]
        for rule_id in receipt.rule_chain:
            if rule_id not in rule_ids:
                warnings.append(f"rule_chain 中的 {rule_id} 不在 trigger_rules 中")

    # 实际成本校验（如果有）
    if receipt.actual_cost:
        actual_total = receipt.actual_cost.input_cost + receipt.actual_cost.output_cost
        if abs(receipt.actual_cost.total_cost - actual_total) > 0.001:
            warnings.append("actual_cost 内部计算不一致")

    return ValidationReport(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


# ============================================================
# 6. 降级链路校验
# ============================================================

def validate_fallback_chain(receipt: RouteReceipt) -> ValidationReport:
    """
    校验降级链路的合理性

    检查项：
    - 是否有循环（同一模型出现两次）
    - 每一步 from_model != to_model
    - 步骤序号是否连续
    """
    errors = []
    warnings = []

    chain = receipt.fallback_chain
    if not chain:
        return ValidationReport(is_valid=True)

    # 检查闭环循环：to_model 不能指回之前出现过的 from_model
    seen_from_models = set()
    for step in chain:
        if step.to_model in seen_from_models:
            errors.append(
                f"降级链路循环: {step.to_model} 在第 {step.step} 步被回指"
            )
        seen_from_models.add(step.from_model)

    # 检查 from != to
    for step in chain:
        if step.from_model == step.to_model:
            errors.append(
                f"降级步骤 {step.step}: from_model == to_model == {step.from_model}"
            )

    # 检查步骤序号连续性
    expected_steps = list(range(1, len(chain) + 1))
    actual_steps = [s.step for s in chain]
    if actual_steps != expected_steps:
        errors.append(
            f"降级步骤序号不连续: 期望 {expected_steps}, 实际 {actual_steps}"
        )

    # 检查 latency_added_ms 合理性（Pydantic 已校验 ge=0，此处防御）
    for step in chain:
        if step.latency_added_ms < 0:
            errors.append(f"降级步骤 {step.step} latency_added_ms 为负数")

    return ValidationReport(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


# ============================================================
# 7. 全链路集成校验
# ============================================================

class RoutingValidator:
    """
    路由决策校验器 - 全链路校验的统一入口

    支持规则匹配和 LLM 决策两种模式。
    LLM 模式下，策略一致性校验中豁免 decision_reason 与 policy 的严格对应关系。

    用法:
        validator = RoutingValidator()
        report = validator.validate_full(
            request=request,
            features=features,
            receipt=receipt,
        )
        if not report.is_valid:
            raise ValidationError(report)
    """

    def validate_full(
        self,
        request: RouterRequest,
        features: TaskFeatures,
        receipt: RouteReceipt,
    ) -> ValidationReport:
        """
        执行全链路校验

        调用所有子校验，合并结果
        """
        report = ValidationReport(is_valid=True)

        # 1. 请求结构
        report = report.merge(validate_request_structure(request))

        # 2. 特征自洽性
        report = report.merge(validate_task_features(features))

        # 3. 隐私约束（核心）
        report = report.merge(validate_privacy_constraints(features, receipt))

        # 4. 策略一致性
        report = report.merge(validate_policy_consistency(request, receipt))

        # 5. 凭证完整性
        report = report.merge(validate_receipt_consistency(receipt, features))

        # 6. 降级链路
        report = report.merge(validate_fallback_chain(receipt))

        return report

    def validate_privacy_only(
        self,
        features: TaskFeatures,
        receipt: RouteReceipt,
    ) -> ValidationReport:
        """仅执行隐私约束校验（用于快速检查）"""
        return validate_privacy_constraints(features, receipt)

    def validate_receipt_only(
        self,
        receipt: RouteReceipt,
        features: TaskFeatures,
    ) -> ValidationReport:
        """仅执行凭证校验"""
        return validate_receipt_consistency(receipt, features)


# ============================================================
# 自定义异常
# ============================================================

class ValidationError(Exception):
    """校验失败异常"""

    def __init__(self, report: ValidationReport):
        self.report = report
        super().__init__(str(report))

    @property
    def errors(self) -> List[str]:
        return self.report.errors

    @property
    def warnings(self) -> List[str]:
        return self.report.warnings