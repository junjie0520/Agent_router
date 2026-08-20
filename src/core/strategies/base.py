"""
路由策略抽象基类

定义统一的策略接口，支持规则匹配和 LLM 决策两种实现。
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

from src.core.schemas.task import TaskFeatures
from src.core.schemas.receipt import RouteReceipt
from src.core.schemas.request import RouterRequest


class BaseStrategy(ABC):
    """
    路由策略抽象基类

    所有策略实现（规则引擎、LLM 决策器、混合策略等）必须实现此接口。
    策略的职责：
      输入：TaskFeatures + 候选模型列表 + 策略参数
      输出：RouteReceipt（路由凭证）
    """

    @property
    @abstractmethod
    def strategy_name(self) -> str:
        """返回策略名称，用于日志和审计"""
        pass

    @abstractmethod
    def decide(
        self,
        request: RouterRequest,
        features: TaskFeatures,
        candidates: List[Dict[str, Any]],
    ) -> RouteReceipt:
        """
        执行路由决策

        Args:
            request: 原始路由请求，包含策略、预算、元数据等
            features: 从请求中提取的结构化任务特征
            candidates: 候选模型列表，每个元素为模型信息字典

        Returns:
            RouteReceipt: 完整的路由决策凭证

        Raises:
            ValueError: 当候选列表为空或决策无法完成时
        """
        pass

    def get_candidates(
        self,
        candidates: List[Dict[str, Any]],
        policy: str = "balanced",
    ) -> List[Dict[str, Any]]:
        """
        过滤和排序候选模型（可选覆盖）

        默认实现：返回全部候选，不做过滤。
        子类可覆盖以实现策略特定的候选预筛选。

        Args:
            candidates: 原始候选模型列表
            policy: 策略标识

        Returns:
            处理后的候选模型列表
        """
        return candidates