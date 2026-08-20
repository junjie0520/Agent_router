"""
Agent Router - 数据集加载器

从 datasets/ 目录加载 JSONL 评测数据集，解析为 TaskFeatures 或 RouterRequest，
供路由引擎评测、demo 演示和单元测试使用。

支持的格式：
1. 完整请求格式（含 messages）→ RouterRequest
2. 特征格式（预提取的特征）→ TaskFeatures
3. 混合格式（含 content 文本）→ RouterRequest（自动构建 messages）
"""

import json
import logging
from pathlib import Path
from typing import Iterator, List, Optional, Dict, Any, Union
from dataclasses import dataclass, field

from src.core.schemas.request import RouterRequest, Message, MessageRole, RoutingPolicy
from src.core.schemas.task import (
    TaskFeatures, TaskType, PrivacyLevel,
    CodeFeatures, SensitiveFeatures, ToolFeatures, ComplexityMetrics
)

logger = logging.getLogger(__name__)


# ============================================================
# 数据集统计
# ============================================================

@dataclass
class DatasetStatistics:
    """数据集统计信息"""
    total_tasks: int = 0
    by_task_type: Dict[str, int] = field(default_factory=dict)
    by_privacy_level: Dict[str, int] = field(default_factory=dict)
    files_loaded: List[str] = field(default_factory=list)
    parse_errors: int = 0
    skipped_empty: int = 0

    def summary(self) -> str:
        """生成人类可读的统计摘要"""
        lines = [
            "=" * 50,
            f"Dataset Statistics",
            f"  Total tasks: {self.total_tasks}",
            f"  Files loaded: {len(self.files_loaded)}",
            f"  Parse errors: {self.parse_errors}",
            f"  Skipped empty: {self.skipped_empty}",
        ]
        if self.by_task_type:
            lines.append("  By task type:")
            for task_type, count in sorted(self.by_task_type.items()):
                lines.append(f"    {task_type}: {count}")
        if self.by_privacy_level:
            lines.append("  By privacy level:")
            for level, count in sorted(self.by_privacy_level.items()):
                lines.append(f"    {level}: {count}")
        lines.append("=" * 50)
        return "\n".join(lines)


# ============================================================
# 数据集加载器
# ============================================================

class DatasetLoader:
    """
    数据集加载器

    支持加载 JSONL 格式的评测数据集，每行为一个 JSON 对象。

    用法:
        loader = DatasetLoader(data_dir="datasets")
        tasks = loader.load_all()                    # 加载所有文件
        code_tasks = loader.load_by_type("code_gen") # 按类型筛选
        for task in loader.iter_tasks():             # 迭代器模式
            process(task)
    """

    # 默认数据集目录（相对于项目根目录）
    DEFAULT_DATA_DIR = Path("datasets")

    # 支持的文件扩展名
    SUPPORTED_EXTENSIONS = {".jsonl", ".json"}

    def __init__(self, data_dir: Optional[Path] = None):
        """
        初始化加载器

        Args:
            data_dir: 数据集目录路径，默认为 datasets/
        """
        self.data_dir = Path(data_dir) if data_dir else self.DEFAULT_DATA_DIR
        self.statistics = DatasetStatistics()

        if not self.data_dir.exists():
            logger.warning(f"数据集目录不存在: {self.data_dir}，将返回空数据集")

    # ----------------------------------------------------------
    # 公共 API：加载所有文件
    # ----------------------------------------------------------

    def load_all(
        self,
        pattern: str = "*.jsonl",
        as_type: str = "request",
    ) -> List[Union[RouterRequest, TaskFeatures]]:
        """
        加载目录下所有匹配的 JSONL 文件

        Args:
            pattern: 文件匹配模式，默认 "*.jsonl"
            as_type: 解析目标类型，"request" 返回 RouterRequest 列表，
                     "features" 返回 TaskFeatures 列表

        Returns:
            解析后的对象列表
        """
        all_objects = []
        files = sorted(self.data_dir.glob(pattern))

        if not files:
            logger.warning(f"在 {self.data_dir} 中未找到匹配 {pattern} 的文件")
            return all_objects

        for filepath in files:
            objects = self._load_single_file(filepath, as_type)
            all_objects.extend(objects)
            self.statistics.files_loaded.append(filepath.name)

        return all_objects

    # ----------------------------------------------------------
    # 公共 API：加载单个文件
    # ----------------------------------------------------------

    def load_file(
        self,
        filename: str,
        as_type: str = "request",
    ) -> List[Union[RouterRequest, TaskFeatures]]:
        """
        加载单个 JSONL 文件

        Args:
            filename: 文件名（相对于 data_dir）或绝对路径
            as_type: 解析目标类型

        Returns:
            解析后的对象列表
        """
        filepath = Path(filename)
        if not filepath.is_absolute():
            filepath = self.data_dir / filename

        if not filepath.exists():
            logger.error(f"文件不存在: {filepath}")
            return []

        objects = self._load_single_file(filepath, as_type)
        self.statistics.files_loaded.append(filepath.name)
        return objects

    # ----------------------------------------------------------
    # 公共 API：按类型筛选
    # ----------------------------------------------------------

    def load_by_type(
        self,
        task_type: Union[str, TaskType, List[str]],
        as_type: str = "request",
    ) -> List[Union[RouterRequest, TaskFeatures]]:
        """
        按任务类型筛选加载

        Args:
            task_type: 单个任务类型字符串/TaskType，或多个类型的列表
            as_type: 解析目标类型

        Returns:
            匹配的任务列表

        Example:
            code_tasks = loader.load_by_type(["code_gen", "code_refactor"])
            sensitive_tasks = loader.load_by_type("sensitive")
        """
        # 统一为字符串集合
        if isinstance(task_type, str):
            target_types = {task_type}
        elif isinstance(task_type, TaskType):
            target_types = {task_type.value}
        else:
            target_types = {
                t.value if isinstance(t, TaskType) else t
                for t in task_type
            }

        all_objects = self.load_all(as_type=as_type)
        filtered = [
            obj for obj in all_objects
            if self._get_task_type(obj) in target_types
        ]
        return filtered

    def load_by_privacy_level(
        self,
        privacy_level: Union[str, PrivacyLevel],
        as_type: str = "request",
    ) -> List[Union[RouterRequest, TaskFeatures]]:
        """
        按隐私等级筛选加载

        Args:
            privacy_level: 隐私等级
            as_type: 解析目标类型

        Returns:
            匹配的任务列表
        """
        if isinstance(privacy_level, PrivacyLevel):
            target = privacy_level.value
        else:
            target = privacy_level

        all_objects = self.load_all(as_type=as_type)
        filtered = [
            obj for obj in all_objects
            if self._get_privacy_level(obj) == target
        ]
        return filtered

    # ----------------------------------------------------------
    # 公共 API：迭代器
    # ----------------------------------------------------------

    def iter_tasks(
        self,
        pattern: str = "*.jsonl",
        as_type: str = "request",
        batch_size: int = 100,
    ) -> Iterator[Union[RouterRequest, TaskFeatures]]:
        """
        迭代器模式加载，适用于大规模数据集

        Args:
            pattern: 文件匹配模式
            as_type: 解析目标类型
            batch_size: 预留参数（当前按文件级迭代）

        Yields:
            逐个解析后的对象
        """
        files = sorted(self.data_dir.glob(pattern))
        for filepath in files:
            for line_num, line in enumerate(self._read_lines(filepath), start=1):
                if not line.strip():
                    continue
                obj = self._parse_line(line, line_num, filepath.name, as_type)
                if obj is not None:
                    yield obj

    # ----------------------------------------------------------
    # 公共 API：统计
    # ----------------------------------------------------------

    def get_statistics(self) -> DatasetStatistics:
        """返回数据集统计信息（需先调用 load_all 或 load_file）"""
        return self.statistics

    def print_statistics(self) -> None:
        """打印统计摘要"""
        print(self.statistics.summary())

    # ----------------------------------------------------------
    # 内部方法：文件读取
    # ----------------------------------------------------------

    def _load_single_file(
        self,
        filepath: Path,
        as_type: str,
    ) -> List[Union[RouterRequest, TaskFeatures]]:
        """加载单个文件的内部实现"""
        objects = []
        filename = filepath.name

        for line_num, line in enumerate(self._read_lines(filepath), start=1):
            if not line.strip():
                self.statistics.skipped_empty += 1
                continue

            obj = self._parse_line(line, line_num, filename, as_type)
            if obj is not None:
                objects.append(obj)
                self.statistics.total_tasks += 1
                self._update_statistics(obj)

        return objects

    @staticmethod
    def _read_lines(filepath: Path) -> Iterator[str]:
        """读取文件行（处理编码问题）"""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    yield line
        except UnicodeDecodeError:
            logger.warning(f"UTF-8 解码失败，尝试 latin-1: {filepath}")
            with open(filepath, "r", encoding="latin-1") as f:
                for line in f:
                    yield line

    # ----------------------------------------------------------
    # 内部方法：行解析
    # ----------------------------------------------------------

    def _parse_line(
        self,
        line: str,
        line_num: int,
        filename: str,
        as_type: str,
    ) -> Optional[Union[RouterRequest, TaskFeatures]]:
        """
        解析单行 JSON

        Args:
            line: JSON 字符串
            line_num: 行号（用于错误报告）
            filename: 文件名（用于错误报告）
            as_type: 目标类型

        Returns:
            解析成功返回对象，失败返回 None
        """
        try:
            data = json.loads(line)
        except json.JSONDecodeError as e:
            self.statistics.parse_errors += 1
            logger.warning(f"JSON 解析失败 [{filename}:{line_num}]: {e}")
            return None

        try:
            if as_type == "features":
                return self._parse_as_features(data, filename, line_num)
            else:
                return self._parse_as_request(data, filename, line_num)
        except Exception as e:
            self.statistics.parse_errors += 1
            logger.warning(f"对象构建失败 [{filename}:{line_num}]: {e}")
            return None

    # ----------------------------------------------------------
    # 内部方法：构建 RouterRequest
    # ----------------------------------------------------------

    @staticmethod
    def _parse_as_request(
        data: Dict[str, Any],
        filename: str,
        line_num: int,
    ) -> Optional[RouterRequest]:
        """
        从 JSON 构建 RouterRequest

        支持两种格式：
        1. 完整格式：包含 messages 字段
        2. 简化格式：包含 content 字段，自动包装为单条 user message
        """
        # 完整格式：直接有 messages
        if "messages" in data:
            return RouterRequest(**data)

        # 简化格式：从 content 构建
        if "content" in data:
            task_id = data.get("task_id", f"task_{line_num}")
            policy = data.get("policy", "balanced")
            metadata = data.get("metadata", {})

            # 如果有 task_type，放入 metadata
            if "task_type" in data:
                metadata["task_type"] = data["task_type"]
            if "privacy_level" in data:
                metadata["privacy_level"] = data["privacy_level"]
            if "expected_model" in data:
                metadata["expected_model"] = data["expected_model"]

            return RouterRequest(
                request_id=task_id,
                messages=[
                    Message(role=MessageRole.USER, content=data["content"])
                ],
                policy=RoutingPolicy(policy) if isinstance(policy, str) else policy,
                metadata=metadata if metadata else None,
            )

        logger.warning(f"数据缺少 messages 或 content 字段 [{filename}:{line_num}]")
        return None

    # ----------------------------------------------------------
    # 内部方法：构建 TaskFeatures
    # ----------------------------------------------------------

    @staticmethod
    def _parse_as_features(
        data: Dict[str, Any],
        filename: str,
        line_num: int,
    ) -> Optional[TaskFeatures]:
        """
        从 JSON 构建 TaskFeatures

        支持两种格式：
        1. 完整格式：包含 complexity、code_features 等嵌套结构
        2. 简化格式：扁平字段，自动构建子模型
        """
        # 完整格式
        if "complexity" in data or "code_features" in data:
            return TaskFeatures(**data)

        # 简化格式：从扁平字段构建
        task_type = TaskType(data.get("task_type", "unknown"))
        privacy_level = PrivacyLevel(data.get("privacy_level", "none"))

        # 构建子模型
        complexity = ComplexityMetrics(
            complexity_score=float(data.get("complexity_score", 0)),
            token_count=int(data.get("token_count", 0)),
            message_count=int(data.get("message_count", 1)),
        )

        code_features = CodeFeatures(
            has_code=data.get("has_code", False),
            code_languages=data.get("code_languages", []),
            code_block_count=data.get("code_block_count", 0),
        )

        sensitive = SensitiveFeatures(
            has_pii=data.get("has_pii", False),
            pii_types=data.get("pii_types", []),
            has_credentials=data.get("has_credentials", False),
            risk_score=float(data.get("risk_score", 0)),
        )

        tool_features = ToolFeatures(
            tool_count=data.get("tool_count", 0),
            tool_names=data.get("tool_names", []),
        )

        return TaskFeatures(
            task_type=task_type,
            privacy_level=privacy_level,
            complexity=complexity,
            code_features=code_features,
            sensitive=sensitive,
            tool_features=tool_features,
            keywords_matched=data.get("keywords_matched", []),
            extraction_metadata=data.get("extraction_metadata", {}),
        )

    # ----------------------------------------------------------
    # 内部方法：统计更新
    # ----------------------------------------------------------

    def _update_statistics(
        self,
        obj: Union[RouterRequest, TaskFeatures],
    ) -> None:
        """更新统计计数器"""
        task_type = self._get_task_type(obj)
        privacy_level = self._get_privacy_level(obj)

        if task_type:
            self.statistics.by_task_type[task_type] = \
                self.statistics.by_task_type.get(task_type, 0) + 1
        if privacy_level:
            self.statistics.by_privacy_level[privacy_level] = \
                self.statistics.by_privacy_level.get(privacy_level, 0) + 1

    @staticmethod
    def _get_task_type(obj: Union[RouterRequest, TaskFeatures]) -> str:
        """从对象中提取任务类型字符串"""
        if isinstance(obj, TaskFeatures):
            return obj.task_type.value

        if isinstance(obj, RouterRequest) and obj.metadata:
            return str(obj.metadata.get("task_type", "unknown"))

        return "unknown"

    @staticmethod
    def _get_privacy_level(obj: Union[RouterRequest, TaskFeatures]) -> str:
        """从对象中提取隐私等级字符串"""
        if isinstance(obj, TaskFeatures):
            return obj.privacy_level.value

        if isinstance(obj, RouterRequest) and obj.metadata:
            return str(obj.metadata.get("privacy_level", "none"))

        return "none"


# ============================================================
# 便捷函数
# ============================================================

def load_dataset(
    data_dir: str = "datasets",
    task_type: Optional[str] = None,
    privacy_level: Optional[str] = None,
    as_type: str = "request",
) -> List[Union[RouterRequest, TaskFeatures]]:
    """
    便捷加载函数

    Args:
        data_dir: 数据集目录
        task_type: 可选的任务类型过滤
        privacy_level: 可选的隐私等级过滤
        as_type: 返回类型

    Returns:
        任务列表

    Example:
        # 加载所有代码任务
        tasks = load_dataset(task_type="code_gen")

        # 加载高敏感任务
        tasks = load_dataset(privacy_level="high")
    """
    loader = DatasetLoader(Path(data_dir))

    if task_type:
        return loader.load_by_type(task_type, as_type=as_type)
    elif privacy_level:
        return loader.load_by_privacy_level(privacy_level, as_type=as_type)
    else:
        return loader.load_all(as_type=as_type)


def load_dataset_as_requests(data_dir: str = "datasets") -> List[RouterRequest]:
    """加载数据集并返回 RouterRequest 列表（类型安全包装）"""
    return load_dataset(data_dir=data_dir, as_type="request")


def load_dataset_as_features(data_dir: str = "datasets") -> List[TaskFeatures]:
    """加载数据集并返回 TaskFeatures 列表（类型安全包装）"""
    return load_dataset(data_dir=data_dir, as_type="features")


# ============================================================
# 使用示例
# ============================================================

if __name__ == "__main__":
    # 示例：加载并打印统计
    loader = DatasetLoader()
    tasks = loader.load_all()
    loader.print_statistics()

    # 示例：按类型加载
    code_tasks = loader.load_by_type(["code_gen", "code_refactor"])
    print(f"\n代码任务数量: {len(code_tasks)}")

    # 示例：迭代器模式
    print("\n前 3 个任务:")
    for i, task in enumerate(loader.iter_tasks()):
        if i >= 3:
            break
        if isinstance(task, RouterRequest):
            print(f"  [{task.request_id}] {task.get_last_message().content[:80]}...")