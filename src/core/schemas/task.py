"""
Agent Router - 任务特征数据模型
定义从请求中提取的结构化特征，是路由决策的判断依据
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Any, Optional
from enum import Enum


class TaskType(str, Enum):
    """任务类型枚举"""
    SIMPLE_QA = "simple_qa"           # 简单问答
    CODE_GENERATION = "code_gen"      # 代码生成
    CODE_REFACTOR = "code_refactor"   # 代码重构
    TOOL_USE = "tool_use"            # 工具调用
    LONG_CONTEXT = "long_context"     # 长上下文
    CREATIVE_WRITING = "creative"     # 创意写作
    DATA_ANALYSIS = "data_analysis"  # 数据分析
    TRANSLATION = "translation"       # 翻译
    SUMMARIZATION = "summarization"   # 摘要
    SENSITIVE_HANDLING = "sensitive"  # 敏感数据处理
    UNKNOWN = "unknown"              # 未知类型


class PrivacyLevel(str, Enum):
    """隐私等级枚举"""
    NONE = "none"           # 无敏感信息
    LOW = "low"            # 低敏感（如公开数据）
    MEDIUM = "medium"      # 中敏感（如一般个人信息）
    HIGH = "high"          # 高敏感（如PII、内部配置）
    CRITICAL = "critical"  # 极高敏感（如密钥、凭证）


class CodeFeatures(BaseModel):
    """代码相关特征"""
    has_code: bool = Field(default=False, description="是否包含代码块")
    code_languages: List[str] = Field(default_factory=list, description="代码语言列表")
    code_block_count: int = Field(default=0, ge=0, description="代码块数量，非负")
    total_code_lines: int = Field(default=0, ge=0, description="代码总行数，非负")
    has_multiple_files: bool = Field(default=False, description="是否涉及多文件")
    has_imports: bool = Field(default=False, description="是否包含import语句")
    has_functions: bool = Field(default=False, description="是否包含函数定义")
    has_classes: bool = Field(default=False, description="是否包含类定义")


class SensitiveFeatures(BaseModel):
    """敏感信息特征"""
    has_pii: bool = Field(default=False, description="是否包含个人信息")
    pii_types: List[str] = Field(default_factory=list, description="PII类型列表")
    pii_matches: List[Dict[str, str]] = Field(
        default_factory=list,
        description="PII匹配详情（类型：值）"
    )
    has_credentials: bool = Field(default=False, description="是否包含凭证/密钥")
    has_internal_config: bool = Field(default=False, description="是否包含内部配置")
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0, description="风险评分 0~1")


class ToolFeatures(BaseModel):
    """工具调用特征"""
    tool_count: int = Field(default=0, ge=0, description="工具定义数量，非负")
    tool_names: List[str] = Field(default_factory=list, description="工具名称列表")
    has_complex_tool_chain: bool = Field(
        default=False,
        description="是否涉及复杂工具链"
    )
    requires_state_mutation: bool = Field(
        default=False,
        description="是否需要状态变更"
    )


class ComplexityMetrics(BaseModel):
    """
    基础复杂度度量（纯统计数据）
    
    注意：complexity_score 不在此模型中，由 ComplexityAnalyzer 独立计算后填入 TaskFeatures
    """
    token_count: int = Field(default=0, ge=0, description="总token数，非负")
    message_count: int = Field(default=0, ge=0, description="消息轮次，非负")
    avg_message_length: float = Field(default=0.0, ge=0.0, description="平均消息长度")
    vocabulary_diversity: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="词汇多样性 0~1"
    )


class ComplexityResult(BaseModel):
    """
    复杂度分析结果
    
    由 ComplexityAnalyzer 产出，包含评分和分解因子，保证可解释性
    """
    score: float = Field(default=0.0, ge=0.0, le=10.0, description="综合复杂度评分 0~10")
    factors: Dict[str, float] = Field(
        default_factory=dict,
        description="各因子贡献分，如 {'token_count': 3.0, 'message_rounds': 1.5, 'code_complexity': 2.0}"
    )
    reasoning: str = Field(default="", description="复杂度评估理由，LLM模式下为详细解释")


class TaskFeatures(BaseModel):
    """
    任务特征 - 路由决策的核心依据

    包含从原始请求中提取的所有结构化特征。
    complexity_score 由 pipeline 调用 ComplexityAnalyzer 后填入，
    不在 ComplexityMetrics 中，保持统计与评估分离。
    """
    # 基础特征
    task_type: TaskType = Field(default=TaskType.UNKNOWN, description="任务类型")
    task_types_hints: List[TaskType] = Field(
        default_factory=list,
        description="可能的任务类型（置信度排序）"
    )

    # 复杂度特征（纯统计 + 独立评估）
    complexity: ComplexityMetrics = Field(
        default_factory=ComplexityMetrics,
        description="基础复杂度度量（纯统计）"
    )
    complexity_score: float = Field(
        default=0.0,
        ge=0.0,
        le=10.0,
        description="综合复杂度评分 0~10（由 ComplexityAnalyzer 计算）"
    )
    complexity_result: Optional[ComplexityResult] = Field(
        default=None,
        description="复杂度分析详情（含因子分解，LLM模式下含推理过程）"
    )

    # 领域特征
    code_features: CodeFeatures = Field(
        default_factory=CodeFeatures,
        description="代码特征"
    )
    tool_features: ToolFeatures = Field(
        default_factory=ToolFeatures,
        description="工具特征"
    )

    # 安全特征
    sensitive: SensitiveFeatures = Field(
        default_factory=SensitiveFeatures,
        description="敏感信息特征"
    )
    privacy_level: PrivacyLevel = Field(
        default=PrivacyLevel.NONE,
        description="隐私等级"
    )

    # 关键词特征
    keywords_matched: List[str] = Field(
        default_factory=list,
        description="匹配到的关键词"
    )

    # 元数据
    extraction_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="特征提取元数据（如各提取器版本、耗时等）"
    )

    def to_rule_input(self) -> Dict[str, Any]:
        """
        转换为规则匹配输入格式
        将嵌套结构展平为规则引擎可直接使用的键值对
        """
        return {
            # 复杂度
            "token_count": self.complexity.token_count,
            "message_count": self.complexity.message_count,
            "complexity_score": self.complexity_score,

            # 任务类型
            "task_type": self.task_type.value,
            "is_code_task": self.task_type in [
                TaskType.CODE_GENERATION,
                TaskType.CODE_REFACTOR
            ],

            # 代码特征
            "has_code": self.code_features.has_code,
            "code_block_count": self.code_features.code_block_count,
            "has_multiple_files": self.code_features.has_multiple_files,

            # 工具特征
            "has_tools": self.tool_features.tool_count > 0,
            "tool_count": self.tool_features.tool_count,

            # 隐私特征
            "privacy_level": self.privacy_level.value,
            "has_pii": self.sensitive.has_pii,
            "risk_score": self.sensitive.risk_score,
            "pii_types": self.sensitive.pii_types,

            # 其他
            "is_long_context": self.complexity.token_count > 8000,
            "keywords": self.keywords_matched,
        }

    def to_llm_context(self) -> Dict[str, Any]:
        """
        转换为 LLM 决策可用的结构化上下文
        比 to_rule_input 更丰富，保留嵌套结构和复杂度因子
        """
        context = self.to_rule_input()
        
        # 补充规则输入中缺失的信息
        context.update({
            "vocabulary_diversity": self.complexity.vocabulary_diversity,
            "avg_message_length": self.complexity.avg_message_length,
            "task_types_hints": [t.value for t in self.task_types_hints],
            "code_languages": self.code_features.code_languages,
            "has_imports": self.code_features.has_imports,
            "has_functions": self.code_features.has_functions,
            "has_classes": self.code_features.has_classes,
            "tool_names": self.tool_features.tool_names,
            "has_complex_tool_chain": self.tool_features.has_complex_tool_chain,
            "has_credentials": self.sensitive.has_credentials,
            "has_internal_config": self.sensitive.has_internal_config,
        })
        
        # 复杂度因子分解（LLM 模式下的推理依据）
        if self.complexity_result:
            context["complexity_factors"] = self.complexity_result.factors
            context["complexity_reasoning"] = self.complexity_result.reasoning
        
        return context

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "task_type": "code_refactor",
                "task_types_hints": ["code_refactor", "code_gen"],
                "complexity": {
                    "token_count": 1500,
                    "message_count": 3,
                    "avg_message_length": 500.0,
                    "vocabulary_diversity": 0.8
                },
                "complexity_score": 7.5,
                "complexity_result": {
                    "score": 7.5,
                    "factors": {
                        "token_count": 2.0,
                        "message_rounds": 1.5,
                        "code_complexity": 3.0,
                        "vocabulary_diversity": 1.0
                    },
                    "reasoning": "中长文本 + 多轮对话 + 代码重构任务，综合复杂度较高"
                },
                "code_features": {
                    "has_code": True,
                    "code_languages": ["python"],
                    "code_block_count": 2,
                    "total_code_lines": 45,
                    "has_multiple_files": False,
                    "has_imports": True,
                    "has_functions": True,
                    "has_classes": False
                },
                "tool_features": {
                    "tool_count": 0,
                    "tool_names": []
                },
                "sensitive": {
                    "has_pii": False,
                    "pii_types": [],
                    "risk_score": 0.0
                },
                "privacy_level": "none",
                "keywords_matched": ["refactor", "optimize"]
            }
        }
    )