"""
文本统计特征提取器
纯确定性计算：token估算、词汇多样性、消息统计
不包含任何"判断"逻辑（复杂度评分已移至 complexity_analyzer.py）
"""
import re
from typing import List
from src.core.schemas.request import Message
from src.core.schemas.task import ComplexityMetrics


class TextStatsExtractor:
    """文本统计特征提取器"""
    
    # 中文字符正则
    CHINESE_CHAR_PATTERN = re.compile(r'[\u4e00-\u9fff]')
    # 英文单词分割正则（仅ASCII，排除中文）
    WORD_PATTERN = re.compile(r'\b\w+\b', re.ASCII)
    
    def extract(self, messages: List[Message]) -> ComplexityMetrics:
        """
        从消息列表提取基础统计指标
        
        Args:
            messages: 对话消息列表
            
        Returns:
            ComplexityMetrics: 纯统计数据（不含 complexity_score）
        """
        if not messages:
            return ComplexityMetrics(
                token_count=0,
                message_count=0,
                avg_message_length=0.0,
                vocabulary_diversity=0.0,
            )
        
        # 合并所有消息内容
        all_text = " ".join(m.content for m in messages if m.content)
        
        # 基础统计
        token_count = self._estimate_tokens(all_text)
        message_count = len(messages)
        total_length = sum(len(m.content) for m in messages)
        avg_message_length = total_length / message_count if message_count > 0 else 0.0
        
        # 词汇多样性
        vocabulary_diversity = self._calc_vocabulary_diversity(all_text)
        
        return ComplexityMetrics(
            token_count=token_count,
            message_count=message_count,
            avg_message_length=round(avg_message_length, 1),
            vocabulary_diversity=vocabulary_diversity,
        )
    
    # ================================================================
    # Token 估算
    # ================================================================
    
    def _estimate_tokens(self, text: str) -> int:
        """
        估算文本的 token 数量
        
        策略：
        - 英文：字符数 / 4
        - 中文：每个字符算 1.5 token
        - 混合：英文部分按字符/4，中文部分按字符数*1.5
        - 空文本返回 1（最小 token 数）
        """
        text = text.strip()
        if not text:
            return 1
        
        # 分离中文和非中文字符
        chinese_chars = len(self.CHINESE_CHAR_PATTERN.findall(text))
        non_chinese_chars = len(text) - chinese_chars
        
        # 中文 token 估算：每个中文字符 ~1.5 token
        chinese_tokens = chinese_chars * 1.5
        
        # 非中文 token 估算：每 4 字符 ~1 token
        non_chinese_tokens = non_chinese_chars / 4.0
        
        estimated = int(chinese_tokens + non_chinese_tokens)
        return max(estimated, 1)
    
    # ================================================================
    # 词汇多样性
    # ================================================================
    
    def _calc_vocabulary_diversity(self, text: str) -> float:
        """
        计算词汇多样性（Type-Token Ratio 的简化版）
        
        只统计英文单词，中文不参与（中文词汇多样性需要分词，暂不实现）
        
        Args:
            text: 输入文本
            
        Returns:
            float: 0.0~1.0，单词数 < 5 时按比例打折
        """
        text = text.strip()
        if not text:
            return 0.0
        
        # 提取所有英文单词（仅ASCII）
        words = self.WORD_PATTERN.findall(text.lower())
        
        if not words:
            return 0.0
        
        unique_words = set(words)
        ratio = len(unique_words) / len(words)
        
        # 样本量不足时打折
        if len(words) < 5:
            ratio *= len(words) / 5.0
        
        return round(min(ratio, 1.0), 2)