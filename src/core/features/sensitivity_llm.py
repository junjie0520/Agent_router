"""
LLM 敏感信息精判器
正则初筛命中后，用 LLM 做最终分类
"""
import json
import re
import logging
from typing import List, Optional
from src.core.adapters.llm_adapter import BaseLLMAdapter
from src.core.schemas.task import SensitiveFeatures

logger = logging.getLogger(__name__)


class SensitivityLLMJudge:
    """LLM 敏感信息精判器"""

    JSON_PATTERN = re.compile(r'\{[\s\S]*?\}', re.DOTALL)

    def __init__(self, llm_adapter: BaseLLMAdapter):
        self.llm = llm_adapter

    def analyze(self, text: str, regex_hits: List[str]) -> SensitiveFeatures:
        """
        用 LLM 精确判断敏感信息

        Args:
            text: 用户输入文本
            regex_hits: 正则命中的类型列表

        Returns:
            SensitiveFeatures: 精确的敏感信息特征
        """
        prompt = self._build_prompt(text, regex_hits)

        try:
            response = self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=300,
            )
            result = self._parse_response(response.content)
            return self._build_features(result)
        except Exception as e:
            logger.warning(f"LLM敏感精判调用异常，降级使用正则结果: {str(e)}")
            # LLM 失败，回退到正则结果
            return self._fallback_from_regex(regex_hits)

    def _build_prompt(self, text: str, regex_hits: List[str]) -> str:
        hits_str = ", ".join(regex_hits)
        return f"""分析以下文本是否包含真实的敏感信息。

文本：
{text[:2000]}

正则已命中类型：{hits_str}

请严格返回JSON，判断这些命中是真实敏感信息还是误报：

{{
    "has_pii": true/false,
    "pii_types": ["phone", "email", "id_card", "ip_address"],
    "has_credentials": true/false,
    "credential_types": ["api_key", "password", "token", "db_connection"],
    "has_internal_config": true/false,
    "risk_level": "none/low/medium/high/critical",
    "reasoning": "简短判断理由"
}}

注意：
- 测试/示例/占位符数据不算真实敏感信息
- 真实的密钥、密码、身份证号才算
- risk_level: critical=真实凭证泄露, high=真实PII, medium=疑似, low=可能误报, none=无风险

只返回JSON，不要额外解释、markdown标记。"""

    def _parse_response(self, content: str) -> dict:
        content = content.strip()
        match = self.JSON_PATTERN.search(content)
        if not match:
            logger.debug("LLM输出未捕获JSON块")
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError as e:
            logger.debug(f"JSON解析失败: {e}, raw={content[:300]}")
            return {}

    def _build_features(self, result: dict) -> SensitiveFeatures:
        pii_types = result.get("pii_types", [])
        credential_types = result.get("credential_types", [])
        risk_level = result.get("risk_level", "none")
        has_internal_config = result.get("has_internal_config", False)

        risk_score_map = {
            "critical": 1.0,
            "high": 0.8,
            "medium": 0.5,
            "low": 0.2,
            "none": 0.0,
        }
        risk_score = risk_score_map.get(risk_level, 0.0)

        # pii_matches 只存放PII，凭证单独区分，不再混用
        pii_matches = [{"type": t, "value": "***"} for t in pii_types]

        return SensitiveFeatures(
            has_pii=result.get("has_pii", False),
            pii_types=pii_types,
            pii_matches=pii_matches,
            has_credentials=result.get("has_credentials", False),
            has_internal_config=has_internal_config,
            risk_score=risk_score,
        )

    def _fallback_from_regex(self, regex_hits: List[str]) -> SensitiveFeatures:
        pii_map = {"phone", "email", "id_card", "ip_address"}
        cred_map = {"api_key", "aws_access_key", "aws_secret", "jwt_token",
                    "password", "private_key", "db_connection", "github_token"}

        pii = [h for h in regex_hits if h in pii_map]
        cred = [h for h in regex_hits if h in cred_map]

        risk = 0.0
        if cred:
            risk = 0.9
        elif pii:
            risk = 0.5

        pii_matches = [{"type": t, "value": "***"} for t in pii]

        return SensitiveFeatures(
            has_pii=len(pii) > 0,
            pii_types=pii,
            pii_matches=pii_matches,
            has_credentials=len(cred) > 0,
            has_internal_config=False,
            risk_score=risk,
        )