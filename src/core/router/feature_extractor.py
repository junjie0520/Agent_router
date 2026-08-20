"""
特征提取调度器 - 新架构版
只做基础统计和代码检测，敏感信息和复杂度由 LLMAnalyzer 负责
"""
import time
from typing import List, Optional
from src.core.schemas.request import Message, RouterRequest
from src.core.schemas.task import (
    TaskFeatures, TaskType, PrivacyLevel,
)
from src.core.features.text_stats import TextStatsExtractor
from src.core.features.code_detector import CodeDetector


class FeatureExtractor:
    """
    特征提取调度器

    新架构下只负责：
    1. 文本统计（token数、消息轮次、词汇多样性）
    2. 代码检测（代码块匹配）
    
    敏感信息和复杂度判断由 LLMAnalyzer 负责。
    """

    def __init__(
        self,
        text_stats: Optional[TextStatsExtractor] = None,
        code_detector: Optional[CodeDetector] = None,
    ):
        self.text_stats = text_stats or TextStatsExtractor()
        self.code_detector = code_detector or CodeDetector()

    def extract(self, request: RouterRequest) -> TaskFeatures:
        messages = request.messages
        start_time = time.time()
        metadata = {}

        t0 = time.time()
        metrics = self.text_stats.extract(messages)
        metadata['text_stats_ms'] = round((time.time() - t0) * 1000, 1)

        t0 = time.time()
        code_features = self.code_detector.extract(messages)
        metadata['code_detector_ms'] = round((time.time() - t0) * 1000, 1)

        metadata['total_ms'] = round((time.time() - start_time) * 1000, 1)

        # 任务类型推断（简单规则，LLMAnalyzer 会覆盖复杂度判断）
        task_type, task_hints = self._infer_task_type(code_features, metrics, request)

        return TaskFeatures(
            task_type=task_type,
            task_types_hints=task_hints,
            complexity=metrics,
            complexity_score=0.0,  # 由 LLMAnalyzer 填入
            code_features=code_features,
            privacy_level=PrivacyLevel.NONE,  # 由 LLMAnalyzer 填入
            extraction_metadata=metadata,
        )

    def _infer_task_type(self, code_features, metrics, request: RouterRequest):
        hints = []
        full_text = request.get_full_text().lower()

        if code_features.has_code:
            if code_features.has_multiple_files or code_features.total_code_lines > 100:
                hints.append(TaskType.CODE_REFACTOR)
            else:
                hints.append(TaskType.CODE_GENERATION)

        code_intent_kw = [
            '写一个', '实现一个', '编写', '函数', '算法',
            '冒泡', '排序', '快速排序', '二分', '递归', '遍历',
            'debug', '修复bug', '重构',
            'function', 'algorithm', 'implement', 'code',
        ]
        if not code_features.has_code:
            if any(kw in full_text for kw in code_intent_kw):
                if TaskType.CODE_GENERATION not in hints:
                    hints.append(TaskType.CODE_GENERATION)

        if request.has_tools():
            hints.append(TaskType.TOOL_USE)

        if not hints:
            if metrics.token_count < 500 and metrics.message_count <= 2:
                hints.append(TaskType.SIMPLE_QA)
            else:
                hints.append(TaskType.UNKNOWN)

        primary = hints[0] if hints else TaskType.UNKNOWN
        return primary, hints