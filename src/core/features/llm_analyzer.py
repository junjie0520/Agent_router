# src/core/features/llm_analyzer.py

"""
LLM 分析器 - 分析用户请求文本
支持单条文本和多轮对话
"""
import json
import re
import logging
from typing import List, Dict, Union

logger = logging.getLogger(__name__)


class TaskAnalysis:
    """LLM 分析结果"""
    def __init__(self, complexity=0, privacy_level="none", reasoning="",
                 pii_types=None, has_code=False, raw_response=""):
        self.complexity = complexity
        self.privacy_level = privacy_level
        self.reasoning = reasoning
        self.pii_types = pii_types or []
        self.has_code = has_code
        self.raw_response = raw_response


class LLMAnalyzer:
    """LLM 分析器"""

    def __init__(self, llm_adapter):
        self.llm = llm_adapter

    def analyze(self, messages: Union[str, List[Dict[str, str]]]) -> TaskAnalysis:
        """
        分析用户请求
        
        Args:
            messages: 单条文本(str) 或 多轮对话(list[dict])
            
        Returns:
            TaskAnalysis (永远不会返回 None)
        """
        # 统一转成 user_text + context
        if isinstance(messages, str):
            user_text = messages
            context = ""
        elif isinstance(messages, list) and len(messages) > 0:
            history = messages[:-1]
            last = messages[-1]
            user_text = last.get("content", "") if isinstance(last, dict) else str(last)
            context = self._format_history(history)
        else:
            user_text = ""
            context = ""

        # 调 LLM 分析
        try:
            print(f"[LLMAnalyzer] 开始分析: {user_text[:80]}...")
            prompt = self._build_prompt(user_text, context)
            response = self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=300,
            )
            raw = response.content
            print(f"[LLM_RAW] {raw[:300]}")
            logger.debug(f"LLM raw: {raw}")
            return self._parse_response(raw)
        except Exception as e:
            print(f"[LLMAnalyzer ERROR] {e}")
            logger.error(f"LLMAnalyzer: {e}")
            return self._fallback_analyze(user_text)

    def _format_history(self, history: List[Dict[str, str]]) -> str:
        """格式化对话历史"""
        if not history:
            return ""
        lines = ["【对话历史】"]
        for msg in history[-6:]:
            role = msg.get("role", "user") if isinstance(msg, dict) else "unknown"
            content = str(msg.get("content", "")) if isinstance(msg, dict) else str(msg)
            content = content[:200]
            role_label = {"user": "用户", "assistant": "助手", "system": "系统"}.get(role, role)
            lines.append(f"- {role_label}: {content}")
        return "\n".join(lines)

    def _build_prompt(self, text: str, context: str = "") -> str:
        cut_text = text[:1000]
        print(f"[PROMPT] user_text={cut_text[:100]}")
        print(f"[PROMPT] context={context[:200]}")
        return f"""你是一个专业的文本分类器。分析以下用户请求，输出 JSON。

{context}

【当前用户请求】
{cut_text}

=== 判定标准（严格遵守）===

complexity (整数 1-7):
  1 = 简单问候/闲聊（如"你好"、"今天天气怎么样"）
  2 = 基础事实问答/简单翻译（如"Python发布时间"）
  3 = 简单解释/格式化/说明
  4 = 需要工具调用(API/数据库/命令行)、代码生成/修改、SQL查询、正则表达式
  5 = 复杂分析/对比/多条件判断、系统设计、重构代码
  6 = 多领域综合、深度技术讨论、长文档分析
  7 = 顶级专业知识的复杂任务
  ⚠️ 如果涉及代码编写或工具调用，复杂度至少为4

privacy_level:
  "none" = 无任何敏感信息
  "medium" = 个人身份信息（身份证号、手机号、邮箱、姓名）、内部商业数据（财务报告）
  "high" = 数据库连接串、密码、API密钥、token、secret key
  "critical" = AWS凭证(AKIA开头)、root密码、支付信息、完整凭证对
  ⚠️ 重要规则：
  - mysql://、postgresql:// 等数据库连接串 → high
  - 包含"财务"、"营收"、"内部"等关键词 → 至少 medium
  - 同时包含 Access Key + Secret Key → critical

has_code (必须严格判断):
  true = 以下任一情况：
    - 编写/修改/重构/修复代码或函数
    - SQL查询/数据库操作
    - 正则表达式编写
    - Shell命令/PowerShell脚本
    - API调用（GitHub API、REST API等）
    - kubectl/docker/git 等命令行工具
    - 数据处理需要编程（去重、排序、筛选等）
  false = 纯理论问答、概念解释、翻译、格式化、简单查询

pii_types: 检测到的敏感信息类型列表
  可选值: ["id_card","phone","email","password","api_key","address","bank_card",
           "database_url","secret_key","credentials","financial_data"]
  没检测到则为 []

reasoning: 一句话说明判断依据（必须提及has_code和privacy_level的判断理由）

=== 输出格式（只输出 JSON，不要任何其他文字）===
{{"complexity":1,"privacy_level":"none","has_code":false,"reasoning":"简短理由","pii_types":[]}}
"""

    def _parse_response(self, raw: str) -> TaskAnalysis:
        """解析 LLM 返回的 JSON"""
        try:
            # 尝试提取 JSON 块
            json_match = re.search(r'\{[^{}]*\}', raw, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(raw)

            return TaskAnalysis(
                complexity=int(data.get("complexity", 3)),
                privacy_level=str(data.get("privacy_level", "none")),
                has_code=bool(data.get("has_code", False)),
                reasoning=str(data.get("reasoning", "")),
                pii_types=data.get("pii_types", []),
                raw_response=raw,
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"JSON 解析失败: {e}")
            return TaskAnalysis(
                complexity=3,
                privacy_level="none",
                has_code=False,
                reasoning=f"解析失败: {str(e)[:50]}",
                raw_response=raw,
            )

    def _fallback_analyze(self, text: str) -> TaskAnalysis:
        """规则兜底分析（LLM 失败时使用）"""
        print(f"[LLMAnalyzer] 使用规则兜底分析: {text[:80]}...")
        text_lower = text.lower()

        # ========== has_code 检测 ==========
        code_keywords = [
            "代码", "编程", "写一个", "函数", "类", "算法",
            "python", "java", "go", "sql", "bug", "debug",
            "kubectl", "docker", "git", "api", "shell",
            "正则", "重构", "查询", "数据库", "命令",
        ]
        has_code = any(kw in text_lower for kw in code_keywords)

        # ========== privacy_level 检测（加强版）==========
        # critical: AWS凭证、root密码
        if any(kw in text_lower for kw in ["akia", "aws", "root password", "支付密码"]):
            privacy_level = "critical"
        # high: 密码、密钥、token、数据库连接串
        elif any(kw in text_lower for kw in [
            "密码", "密钥", "token", "secret", "api_key", "api key",
            "password", "passwd", "mysql://", "postgresql://", "数据库连接",
            "凭证", "access key",
        ]):
            privacy_level = "high"
        # medium: 个人身份信息、内部商业数据
        elif any(kw in text_lower for kw in [
            "身份证", "银行卡", "手机号", "邮箱", "@",
            "财务", "营收", "内部", "客户", "地址",
        ]):
            privacy_level = "medium"
        else:
            privacy_level = "none"

        # ========== complexity 估算 ==========
        if has_code:
            complexity = 4
        elif len(text) > 200:
            complexity = 5
        elif len(text) > 100:
            complexity = 4
        elif len(text) < 20:
            complexity = 1
        else:
            complexity = 2

        return TaskAnalysis(
            complexity=complexity,
            privacy_level=privacy_level,
            has_code=has_code,
            reasoning="规则兜底分析",
            raw_response="FALLBACK",
        )