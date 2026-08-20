"""
路由引擎
系统顶层调度中枢，串联 FeatureExtractor -> DecisionMaker -> 模型调用 -> 响应组装

职责：
  1. 接收 RouterRequest
  2. 调用 FeatureExtractor 提取特征
  3. 调用 DecisionMaker 做出路由决策
  4. 调用模型适配器执行推理
  5. 组装 RouterResponse
  6. 贯穿全链路的审计日志和链路追踪
"""
import time
import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List

from src.core.schemas.request import RouterRequest, Message, MessageRole
from src.core.schemas.response import (
    RouterResponse, ResponseStatus, ModelResponse,
)
from src.core.schemas.receipt import (
    RouteReceipt, FallbackStep, CostBreakdown, DecisionReason,
)
from src.core.schemas.task import TaskFeatures
from src.core.router.feature_extractor import FeatureExtractor
from src.core.router.decision_maker import DecisionMaker, DecisionError
from src.core.adapters.llm_adapter import BaseLLMAdapter, LLMError
from src.core.strategies.llm_decider import LLMDecider
from src.utils.validators import RoutingValidator, ValidationError

logger = logging.getLogger(__name__)


# ============================================================
# 引擎级异常
# ============================================================

class RouterEngineError(Exception):
    """路由引擎异常"""

    def __init__(self, message: str, request_id: str = "", cause: Optional[Exception] = None):
        super().__init__(message)
        self.request_id = request_id
        self.cause = cause


# ============================================================
# 引擎配置
# ============================================================

class EngineConfig:
    """引擎配置"""

    def __init__(
        self,
        max_fallback_depth: int = 3,
        default_model_timeout_ms: float = 30_000,
        enable_audit: bool = True,
        enable_tracing: bool = True,
        strict_privacy: bool = True,
    ):
        self.max_fallback_depth = max_fallback_depth
        self.default_model_timeout_ms = default_model_timeout_ms
        self.enable_audit = enable_audit
        self.enable_tracing = enable_tracing
        self.strict_privacy = strict_privacy


# ============================================================
# 路由引擎
# ============================================================

class RouterEngine:
    """
    路由引擎 - 系统顶层调度中枢

    用法:
        engine = RouterEngine(
            decision_maker=DecisionMaker(...),
            model_adapter=OpenAIAdapter(...),
        )
        response = await engine.route(request)
        # 或同步
        response = engine.route_sync(request)
    """

    def __init__(
        self,
        decision_maker: DecisionMaker,
        model_adapter: Optional[BaseLLMAdapter] = None,
        feature_extractor: Optional[FeatureExtractor] = None,
        validator: Optional[RoutingValidator] = None,
        config: Optional[EngineConfig] = None,
        audit_logger: Any = None,
        tracer: Any = None,
    ):
        self.decision_maker = decision_maker
        self.model_adapter = model_adapter
        self.feature_extractor = feature_extractor or FeatureExtractor()
        self.validator = validator or RoutingValidator()
        self.config = config or EngineConfig()

        self.audit_logger = audit_logger
        self.tracer = tracer

        self.total_requests = 0
        self.successful_requests = 0
        self.blocked_requests = 0
        self.fallback_requests = 0
        self.failed_requests = 0

    # ================================================================
    # 公共 API：异步路由
    # ================================================================

# engine.py route() 方法完整修复

    async def route(self, request: RouterRequest) -> RouterResponse:
        start_time = time.time()
        self.total_requests += 1
        trace_id = request.trace_id or self._generate_trace_id()

        await self._trace_start(trace_id, request)

        try:
            # 阶段 1: 特征提取
            features = self.feature_extractor.extract(request)
            extraction_ms = (time.time() - start_time) * 1000

            # 阶段 2: 路由决策
            receipt = self.decision_maker.decide(request=request, features=features)
            routing_ms = (time.time() - start_time) * 1000 - extraction_ms

            # 阶段 3: 隐私阻断检查
            if not receipt.privacy_checks_passed:
                self.blocked_requests += 1
                response = self._build_blocked_response(request, receipt, trace_id)
                await self._audit_log(request, response, trace_id)
                await self._trace_end(trace_id, response)
                return response

            # 阶段 4: 模型调用（带降级）
            model_response, updated_receipt = await self._call_model_with_fallback(
            request=request, receipt=receipt, trace_id=trace_id,
            )

            # 阶段 5: 组装成功响应
            total_ms = (time.time() - start_time) * 1000
            response = self._build_success_response(
                request=request, receipt=updated_receipt,
                model_response=model_response, trace_id=trace_id,
                total_ms=total_ms, routing_ms=routing_ms,
                extraction_ms=extraction_ms,
            )
            self.successful_requests += 1

            await self._audit_log(request, response, trace_id)
            await self._trace_end(trace_id, response)
            return response

        except DecisionError as e:
            self.failed_requests += 1
            response = self._build_error_response(request, trace_id, str(e), "decision_error")
            await self._audit_log(request, response, trace_id)
            await self._trace_end(trace_id, response)
            return response

        except LLMError as e:
            self.failed_requests += 1
            response = self._build_error_response(request, trace_id, str(e), "model_error")
            await self._audit_log(request, response, trace_id)
            await self._trace_end(trace_id, response)
            return response

        except ValidationError as e:
            self.failed_requests += 1
            response = self._build_error_response(
                request, trace_id, str(e), "validation_error", warnings=e.warnings,
            )
            await self._audit_log(request, response, trace_id)
            await self._trace_end(trace_id, response)
            return response

        except Exception as e:
            self.failed_requests += 1
            logger.exception(f"[{request.request_id}] 未知错误: {e}")
            response = self._build_error_response(request, trace_id, str(e), "unknown_error")
            await self._audit_log(request, response, trace_id)
            await self._trace_end(trace_id, response)
            return response
    # ================================================================
    # 公共 API：同步路由
    # ================================================================

    def route_sync(self, request: RouterRequest) -> RouterResponse:
        """同步路由请求"""
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.route(request))
                    return future.result(timeout=60)
            else:
                return loop.run_until_complete(self.route(request))
        except RuntimeError:
            return asyncio.run(self.route(request))

    # ================================================================
    # 模型调用 + 降级
    # ================================================================

    async def _call_model_with_fallback(
        self,
        request: RouterRequest,
        receipt: RouteReceipt,
        trace_id: str,
    ) -> tuple:
        """调用选中的模型，失败时按候选列表降级"""
        if self.model_adapter is None:
            receipt.extra["model_execution"] = "skipped - no model adapter configured"
            return None, receipt

        fallback_queue = self._build_fallback_queue(receipt)
        errors = []

        for attempt, (model_id, is_fallback) in enumerate(fallback_queue):
            try:
                messages = self._build_model_messages(request)

                if is_fallback and attempt > 0:
                    prev_model = fallback_queue[attempt - 1][0]
                    step = FallbackStep(
                        step=attempt,
                        from_model=prev_model,
                        to_model=model_id,
                        reason=f"模型调用失败: {errors[-1] if errors else '未知'}",
                        timestamp=datetime.now(),
                        latency_added_ms=0,
                    )
                    receipt.fallback_chain.append(step)
                    receipt.is_fallback = True
                    receipt.decision_reason = DecisionReason.FALLBACK
                    receipt.selected_model = model_id
                    self.fallback_requests += 1

                t0 = time.time()
                response = await self._invoke_model(model_id, messages)
                model_ms = (time.time() - t0) * 1000
                receipt.actual_latency_ms = model_ms

                if response.tokens_used:
                    receipt.actual_cost = self._calc_actual_cost(
                        model_id, response.tokens_used, receipt
                    )

                receipt.extra["model_execution"] = {
                    "model": model_id,
                    "attempt": attempt + 1,
                    "is_fallback": is_fallback,
                    "latency_ms": model_ms,
                    "tokens_used": response.tokens_used,
                }

                return response, receipt

            except LLMError as e:
                errors.append(str(e))
                logger.warning(
                    f"[{request.request_id}] 模型 {model_id} 调用失败 (attempt {attempt + 1}): {e}"
                )
                if not e.retryable and attempt >= self.config.max_fallback_depth:
                    break
                continue

            except Exception as e:
                errors.append(str(e))
                logger.error(f"[{request.request_id}] 模型 {model_id} 异常: {e}")
                continue

        raise LLMError(
            f"所有候选模型调用失败 (attempted {len(fallback_queue)}): {'; '.join(errors)}",
            retryable=False,
        )

    def _build_fallback_queue(self, receipt: RouteReceipt) -> List[tuple]:
        """构建降级候选队列"""
        queue = [(receipt.selected_model, False)]

        sorted_candidates = sorted(
            receipt.candidate_models,
            key=lambda c: c.score,
            reverse=True,
        )
        for c in sorted_candidates:
            if c.model_id != receipt.selected_model and c.is_available:
                queue.append((c.model_id, True))

        return queue[:self.config.max_fallback_depth + 1]

    async def _invoke_model(
        self,
        model_id: str,
        messages: List[Dict[str, str]],
    ) -> ModelResponse:
        """调用模型适配器执行推理"""
        if self.model_adapter is None:
            raise LLMError("模型适配器未配置", retryable=False)

        response = self.model_adapter.chat(
            messages=messages,
            temperature=0.7,
            max_tokens=4096,
        )

        return ModelResponse(
            content=response.content,
            finish_reason=response.finish_reason,
            tokens_used=response.tokens_used,
            model=model_id,
        )

    @staticmethod
    def _build_model_messages(request: RouterRequest) -> List[Dict[str, str]]:
        """将 RouterRequest 的 messages 转为适配器可用的格式"""
        return [
            {"role": msg.role.value, "content": msg.content}
            for msg in request.messages
        ]

    @staticmethod
    def _calc_actual_cost(
        model_id: str,
        tokens_used: int,
        receipt: RouteReceipt,
    ) -> CostBreakdown:
        """根据实际 token 用量估算成本"""
        ratio = 0.6
        input_tokens = int(tokens_used * ratio)
        output_tokens = tokens_used - input_tokens

        if receipt.estimated_cost.input_tokens > 0:
            input_unit_cost = receipt.estimated_cost.input_cost / receipt.estimated_cost.input_tokens
        else:
            input_unit_cost = 0
        if receipt.estimated_cost.output_tokens > 0:
            output_unit_cost = receipt.estimated_cost.output_cost / receipt.estimated_cost.output_tokens
        else:
            output_unit_cost = 0

        return CostBreakdown(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            input_cost=round(input_tokens * input_unit_cost, 6),
            output_cost=round(output_tokens * output_unit_cost, 6),
            total_cost=round(input_tokens * input_unit_cost + output_tokens * output_unit_cost, 6),
        )

    # ================================================================
    # 响应组装
    # ================================================================

    def _build_success_response(
        self,
        request: RouterRequest,
        receipt: RouteReceipt,
        model_response: Optional[ModelResponse],
        trace_id: str,
        total_ms: float,
        routing_ms: float,
        extraction_ms: float,
    ) -> RouterResponse:
        """组装成功响应"""
        is_partial = receipt.is_fallback and model_response is not None

        return RouterResponse(
            response_id=self._generate_response_id(),
            request_id=request.request_id,
            status=ResponseStatus.PARTIAL_SUCCESS if is_partial else ResponseStatus.SUCCESS,
            status_message="降级后完成" if is_partial else "成功",
            model_response=model_response,
            receipt=receipt,
            total_latency_ms=round(total_ms, 1),
            routing_latency_ms=round(routing_ms, 1),
            model_latency_ms=receipt.actual_latency_ms or 0,
            extra={
                "trace_id": trace_id,
                "feature_extraction_ms": round(extraction_ms, 1),
                "routing_decision_ms": round(routing_ms, 1),
                "engine_version": "0.1.0",
            },
        )

    def _build_blocked_response(
        self,
        request: RouterRequest,
        receipt: RouteReceipt,
        trace_id: str,
    ) -> RouterResponse:
        """组装隐私阻断响应"""
        return RouterResponse(
            response_id=self._generate_response_id(),
            request_id=request.request_id,
            status=ResponseStatus.BLOCKED,
            status_message="隐私策略阻断",
            model_response=None,
            receipt=receipt,
            is_blocked=True,
            block_reason=receipt.decision_explanation,
            extra={
                "trace_id": trace_id,
                "privacy_level": receipt.privacy_level.value,
                "pii_detected": receipt.pii_detected,
            },
        )

    def _build_error_response(
        self,
        request: RouterRequest,
        trace_id: str,
        error_msg: str,
        error_type: str,
        warnings: Optional[List[str]] = None,
    ) -> RouterResponse:
        """组装错误响应"""
        return RouterResponse(
            response_id=self._generate_response_id(),
            request_id=request.request_id,
            status=ResponseStatus.FAILED,
            status_message=f"{error_type}: {error_msg[:200]}",
            model_response=None,
            receipt=RouteReceipt(
                request_id=request.request_id,
                trace_id=trace_id,
                requested_policy=request.policy,
                effective_policy=request.policy,
                selected_model="",
                decision_reason=DecisionReason.FALLBACK,
                decision_explanation=f"引擎错误: {error_msg[:200]}",
                task_type=TaskFeatures().task_type,
                privacy_level=TaskFeatures().privacy_level,
                complexity_score=0,
                estimated_cost=CostBreakdown(),
                estimated_latency_ms=0,
                errors=[f"[{error_type}] {error_msg}"],
                extra={"trace_id": trace_id, "error_type": error_type},
            ),
            errors=[f"[{error_type}] {error_msg}"],
            warnings=warnings or [],
            extra={"trace_id": trace_id, "error_type": error_type},
        )

    # ================================================================
    # 审计和追踪 hooks
    # ================================================================

    async def _audit_log(self, request: RouterRequest, response: RouterResponse, trace_id: str):
        """写入审计日志"""
        if self.audit_logger is None:
            return

        try:
            receipt = response.receipt
            if receipt is not None:
                # 确保 trace_id 一致
                if not receipt.trace_id:
                    receipt.trace_id = trace_id
                self.audit_logger.log(receipt)
                logger.debug(f"[{request.request_id}] 审计日志已写入: receipt={receipt.receipt_id}")
        except Exception as e:
            logger.error(f"[{request.request_id}] 审计日志写入失败: {e}")

    async def _trace_start(self, trace_id: str, request: RouterRequest):
        """链路追踪开始"""
        if self.tracer is None:
            return

        try:
            await self.tracer.start_trace(trace_id, request)
        except Exception as e:
            logger.debug(f"[{request.request_id}] 追踪启动失败: {e}")

    async def _trace_end(self, trace_id: str, response: RouterResponse):
        """链路追踪结束"""
        if self.tracer is None:
            return

        try:
            await self.tracer.end_trace(trace_id, response)
        except Exception as e:
            logger.debug(f"[{trace_id}] 追踪结束失败: {e}")

    # ================================================================
    # 辅助方法
    # ================================================================

    @staticmethod
    def _generate_trace_id() -> str:
        return f"trace_{uuid.uuid4().hex[:16]}"

    @staticmethod
    def _generate_response_id() -> str:
        return f"resp_{uuid.uuid4().hex[:12]}"

    # ================================================================
    # 统计
    # ================================================================

    def get_stats(self) -> Dict[str, Any]:
        """获取引擎统计信息"""
        dm_stats = self.decision_maker.get_stats()
        return {
            "engine": {
                "total_requests": self.total_requests,
                "successful_requests": self.successful_requests,
                "blocked_requests": self.blocked_requests,
                "fallback_requests": self.fallback_requests,
                "failed_requests": self.failed_requests,
                "success_rate": self.successful_requests / max(self.total_requests, 1),
            },
            "decision_maker": dm_stats,
        }

    def reset_stats(self):
        """重置统计"""
        self.total_requests = 0
        self.successful_requests = 0
        self.blocked_requests = 0
        self.fallback_requests = 0
        self.failed_requests = 0