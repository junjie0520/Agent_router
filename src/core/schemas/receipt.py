"""
Agent Router - 路由凭证数据模型
完整的决策审计记录，保证可解释性、可审计性
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum

from .task import PrivacyLevel, TaskType
from .request import RoutingPolicy


class DecisionReason(str, Enum):
    """决策原因类型"""
    RULE_MATCHED = "rule_matched"           # 规则匹配
    PRIVACY_ENFORCEMENT = "privacy_enforced" # 隐私强制
    BUDGET_CONSTRAINT = "budget_constrained" # 预算约束
    FALLBACK = "fallback"                   # 降级切换
    DEFAULT = "default"                     # 默认策略
    MANUAL_OVERRIDE = "manual_override"     # 手动覆盖
    LLM_DECIDED = "llm_decided"             # LLM智能决策


class RuleTrigger(BaseModel):
    """规则触发记录"""
    rule_id: str = Field(..., description="规则ID")
    rule_name: str = Field(..., description="规则名称")
    priority: int = Field(..., ge=0, description="规则优先级，非负整数")
    conditions_matched: List[str] = Field(..., description="匹配的条件列表")
    feature_values: Dict[str, Any] = Field(..., description="触发的特征值")
    reason: str = Field(..., description="人类可读的触发理由")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "rule_id": "PII_BLOCK",
                "rule_name": "PII信息拦截",
                "priority": 100,
                "conditions_matched": ["privacy_level == 'high'"],
                "feature_values": {
                    "privacy_level": "high",
                    "pii_types": ["phone", "email"]
                },
                "reason": "检测到高敏感个人信息（手机号、邮箱），强制使用本地私有模型"
            }
        }
    )


class ModelCandidate(BaseModel):
    """候选模型"""
    model_id: str = Field(..., description="模型标识")
    score: float = Field(..., ge=0.0, le=1.0, description="匹配得分 0~1")
    estimated_cost: float = Field(..., ge=0.0, description="预估成本（美元）")
    estimated_latency_ms: float = Field(..., ge=0.0, description="预估延迟（毫秒）")
    is_available: bool = Field(default=True, description="是否可用")
    selection_reason: Optional[str] = Field(None, description="选择/排除理由")


class FallbackStep(BaseModel):
    """降级步骤"""
    step: int = Field(..., ge=1, description="降级步骤序号，从1开始")
    from_model: str = Field(..., description="源模型")
    to_model: str = Field(..., description="切换至模型")
    reason: str = Field(..., description="降级原因")
    timestamp: datetime = Field(default_factory=datetime.now, description="降级发生时间")
    latency_added_ms: float = Field(default=0.0, ge=0.0, description="额外增加延迟")


class CostBreakdown(BaseModel):
    """成本明细"""
    input_tokens: int = Field(default=0, ge=0, description="输入token数")
    output_tokens: int = Field(default=0, ge=0, description="输出token数")
    input_cost: float = Field(default=0.0, ge=0.0, description="输入成本")
    output_cost: float = Field(default=0.0, ge=0.0, description="输出成本")
    total_cost: float = Field(default=0.0, ge=0.0, description="总成本")
    currency: str = Field(default="USD", description="货币单位")


class RouteReceipt(BaseModel):
    """
    路由凭证 - 完整的决策审计记录

    包含一次路由决策的所有信息，可导出为标准JSON作为审计凭证
    
    支持两种决策模式：
    - 规则匹配模式：decision_reason 为 RULE_MATCHED/PRIVACY_ENFORCEMENT 等，trigger_rules 非空
    - LLM智能决策模式：decision_reason 为 LLM_DECIDED，trigger_rules 为空，决策详情在 decision_explanation 中
    """
    # 标识信息
    receipt_id: str = Field(
        default_factory=lambda: f"rcpt_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        description="凭证唯一ID"
    )
    request_id: str = Field(..., description="关联的请求ID")
    trace_id: str = Field(..., description="链路追踪ID")
    timestamp: datetime = Field(default_factory=datetime.now, description="决策时间戳")

    # 策略信息
    requested_policy: RoutingPolicy = Field(..., description="请求的路由策略")
    effective_policy: RoutingPolicy = Field(..., description="实际生效的策略")
    policy_override_reason: Optional[str] = Field(None, description="策略覆盖原因")

    # 决策结果
    selected_model: str = Field(..., description="最终选中的模型")
    decision_reason: DecisionReason = Field(..., description="决策原因类型")
    decision_explanation: str = Field(..., description="决策的人类可读解释")

    # 候选模型
    candidate_models: List[ModelCandidate] = Field(
        default_factory=list,
        description="所有候选模型及评分"
    )

    # 规则匹配记录（LLM决策时为空列表）
    trigger_rules: List[RuleTrigger] = Field(
        default_factory=list,
        description="触发的规则列表（LLM决策时为空）"
    )
    rule_chain: List[str] = Field(
        default_factory=list,
        description="规则匹配链路，按优先级排序（LLM决策时为空）"
    )

    # 特征快照
    task_type: TaskType = Field(..., description="任务类型")
    privacy_level: PrivacyLevel = Field(..., description="隐私等级")
    complexity_score: float = Field(..., ge=0.0, le=10.0, description="复杂度评分 0~10")
    features_snapshot: Dict[str, Any] = Field(
        default_factory=dict,
        description="关键特征快照"
    )

    # 隐私与合规
    requires_tee: bool = Field(default=False, description="是否需要可信执行环境")
    pii_detected: List[str] = Field(default_factory=list, description="检测到的PII类型")
    privacy_checks_passed: bool = Field(default=True, description="隐私检查是否通过")
    compliance_notes: Optional[str] = Field(None, description="合规备注")

    # 成本与性能预估
    estimated_cost: CostBreakdown = Field(..., description="预估成本")
    estimated_latency_ms: float = Field(..., ge=0.0, description="预估延迟")
    budget_exceeded: bool = Field(default=False, description="是否超出预算")

    # 实际执行结果（执行后填充）
    actual_cost: Optional[CostBreakdown] = Field(None, description="实际成本")
    actual_latency_ms: Optional[float] = Field(None, ge=0.0, description="实际延迟")

    # 降级链路
    fallback_chain: List[FallbackStep] = Field(
        default_factory=list,
        description="降级步骤链路"
    )
    is_fallback: bool = Field(default=False, description="是否触发降级")

    # 错误信息
    errors: List[str] = Field(default_factory=list, description="错误信息列表")
    warnings: List[str] = Field(default_factory=list, description="警告信息列表")

    # 验证签名（防篡改，预留）
    signature: Optional[str] = Field(None, description="数字签名（预留）")
    signature_algorithm: Optional[str] = Field(None, description="签名算法")

    # 扩展字段（LLM决策时可存放原始响应、决策LLM信息等）
    extra: Dict[str, Any] = Field(default_factory=dict, description="扩展信息")

    def to_audit_log(self) -> Dict[str, Any]:
        """转换为审计日志格式"""
        return {
            "receipt_id": self.receipt_id,
            "request_id": self.request_id,
            "timestamp": self.timestamp.isoformat(),
            "selected_model": self.selected_model,
            "decision_reason": self.decision_reason.value,
            "privacy_level": self.privacy_level.value,
            "decision": self.decision_explanation,
            "rules_triggered": [r.rule_id for r in self.trigger_rules],
            "cost_estimate": self.estimated_cost.total_cost,
            "is_fallback": self.is_fallback,
            "errors": self.errors,
        }

    def to_compact_json(self) -> str:
        """生成紧凑JSON（用于日志存储）"""
        import json
        return json.dumps(self.to_audit_log(), ensure_ascii=False)

    def pretty_print(self) -> str:
        """生成可读的凭证摘要"""
        lines = [
            "=" * 60,
            f"Route Receipt: {self.receipt_id}",
            f"Request: {self.request_id}",
            f"Time: {self.timestamp.isoformat()}",
            "-" * 60,
            f"Policy: {self.requested_policy.value} → {self.effective_policy.value}",
            f"Selected Model: {self.selected_model}",
            f"Decision Reason: {self.decision_reason.value}",
            f"Privacy Level: {self.privacy_level.value}",
            f"Complexity: {self.complexity_score}/10",
            "-" * 60,
            f"Decision: {self.decision_explanation}",
            "-" * 60,
        ]

        if self.trigger_rules:
            lines.append("Triggered Rules:")
            for rule in self.trigger_rules:
                lines.append(f"  [{rule.rule_id}] {rule.reason}")
            lines.append("-" * 60)

        lines.append(f"Estimated Cost: ${self.estimated_cost.total_cost:.4f}")
        lines.append(f"Estimated Latency: {self.estimated_latency_ms}ms")

        if self.is_fallback:
            lines.append(f"⚠ FALLBACK: {len(self.fallback_chain)} step(s)")
            for step in self.fallback_chain:
                lines.append(f"  {step.from_model} → {step.to_model}: {step.reason}")

        if self.errors:
            lines.append("Errors:")
            for error in self.errors:
                lines.append(f"  ❌ {error}")

        lines.append("=" * 60)
        return "\n".join(lines)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "receipt_id": "rcpt_20240101120000",
                "request_id": "req_20240101120000",
                "trace_id": "trace_abc123",
                "timestamp": "2024-01-01T12:00:00",
                "requested_policy": "privacy_strict",
                "effective_policy": "privacy_strict",
                "selected_model": "local-private-llm-v2",
                "decision_reason": "privacy_enforced",
                "decision_explanation": "检测到PII信息(手机号)，已强制路由至本地私有模型",
                "trigger_rules": [
                    {
                        "rule_id": "PII_BLOCK",
                        "rule_name": "PII信息拦截",
                        "priority": 100,
                        "conditions_matched": ["privacy_level == 'high'"],
                        "feature_values": {"privacy_level": "high", "pii_types": ["phone"]},
                        "reason": "检测到高敏感个人信息"
                    }
                ],
                "privacy_level": "high",
                "complexity_score": 2.0,
                "pii_detected": ["phone"],
                "estimated_cost": {
                    "input_tokens": 150,
                    "output_tokens": 50,
                    "input_cost": 0.0,
                    "output_cost": 0.0,
                    "total_cost": 0.0
                },
                "estimated_latency_ms": 200,
                "is_fallback": False
            }
        }
    )