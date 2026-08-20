"""
敏感信息扫描器
从消息文本中检测 PII、凭证、内部配置等敏感信息
纯规则匹配（正则），无外部依赖
"""
import re
from typing import List, Dict, Tuple
from src.core.schemas.request import Message
from src.core.schemas.task import SensitiveFeatures, PrivacyLevel


class SensitivityScanner:
    """敏感信息扫描器"""

    # ================================================================
    # PII 检测规则
    # ================================================================

    PHONE_CN_PATTERN = re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)')
    EMAIL_PATTERN = re.compile(r'\b[\w.-]+@[\w.-]+\.\w{2,}\b')
    ID_CARD_CN_PATTERN = re.compile(
        r'(?<!\d)[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)'
    )
    IP_PATTERN = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')

    # ================================================================
    # 凭证 / 密钥检测规则
    # ================================================================

    CREDENTIAL_PATTERNS: List[Tuple[re.Pattern, str]] = [
        (re.compile(r'(?:api[_-]?key|apikey|api[_-]?secret)\s*[:=]\s*[\'"]?[a-zA-Z0-9_-]{16,}[\'"]?', re.IGNORECASE), 'api_key'),
        (re.compile(r'AKIA[0-9A-Z]{16}'), 'aws_access_key'),
        (re.compile(r'(?:aws[_-]?secret|secret[_-]?key)\s*[:=]\s*[\'"]?[\w+/=]{20,}[\'"]?', re.IGNORECASE), 'aws_secret'),
        (re.compile(r'eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}'), 'jwt_token'),
        (re.compile(r'(?:password|passwd|pwd|secret|token)\s*[:=]\s*[\'"]?\S{4,}[\'"]?', re.IGNORECASE), 'password'),
        (re.compile(r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----', re.IGNORECASE), 'private_key'),
        (re.compile(r'(?:mysql|postgres|mongodb|redis)://[^\s]+', re.IGNORECASE), 'db_connection'),
        (re.compile(r'gh[pousr]_[A-Za-z0-9_]{20,}'), 'github_token'),
    ]

    # ================================================================
    # 内部配置检测规则
    # ================================================================

    INTERNAL_CONFIG_PATTERNS: List[Tuple[re.Pattern, str]] = [
        (re.compile(r'(?:db|database|redis|mongo|mysql|postgres)[_-]?(?:host|port|url|uri)\s*[:=]', re.IGNORECASE), 'db_config'),
        (re.compile(r'(?:server|service|app|application)\s*[_-]?(?:host|port|url|endpoint)\s*[:=]', re.IGNORECASE), 'server_config'),
        (re.compile(r'(?:access|secret|encrypt|decrypt)\s*[_-]?key\s*[:=]', re.IGNORECASE), 'crypto_config'),
        (re.compile(r'(?:ssl|tls|cert|certificate|ca)[_-]?(?:file|path|key|cert)\s*[:=]', re.IGNORECASE), 'ssl_config'),
        (re.compile(r'\b(?:0x)?[a-f0-9]{64}\b', re.IGNORECASE), 'hash_hex'),
    ]

    # ================================================================
    # 主入口
    # ================================================================

    def extract(self, messages: List[Message]) -> SensitiveFeatures:
        """从消息列表提取敏感信息特征"""
        full_text = "\n".join(m.content for m in messages if m.content)

        pii_matches, pii_types = self._detect_pii(full_text)
        credential_matches, credential_types = self._detect_credentials(full_text)
        config_matches, config_types = self._detect_internal_config(full_text)

        all_matches = pii_matches + credential_matches + config_matches

        has_pii = len(pii_types) > 0
        has_credentials = len(credential_types) > 0
        has_internal_config = len(config_types) > 0

        risk_score = self._calc_risk_score(pii_types, credential_types, config_types)

        return SensitiveFeatures(
            has_pii=has_pii,
            pii_types=pii_types,
            pii_matches=all_matches,
            has_credentials=has_credentials,
            has_internal_config=has_internal_config,
            risk_score=round(risk_score, 2),
        )

    # ================================================================
    # PII 检测
    # ================================================================

    def _detect_pii(self, text: str) -> Tuple[List[Dict], List[str]]:
        matches = []
        types = []

        for phone in self.PHONE_CN_PATTERN.findall(text)[:3]:
            matches.append({"type": "phone", "value": self._mask(phone, 3, 4)})
        if self.PHONE_CN_PATTERN.search(text):
            types.append("phone")

        for email in self.EMAIL_PATTERN.findall(text)[:3]:
            matches.append({"type": "email", "value": self._mask_email(email)})
        if self.EMAIL_PATTERN.search(text):
            types.append("email")

        for idc in self.ID_CARD_CN_PATTERN.findall(text)[:3]:
            matches.append({"type": "id_card", "value": self._mask(idc, 4, 4)})
        if self.ID_CARD_CN_PATTERN.search(text):
            types.append("id_card")

        ips = self.IP_PATTERN.findall(text)
        public_ips = [ip for ip in ips if not self._is_private_ip(ip)]
        for ip in public_ips[:3]:
            matches.append({"type": "ip_address", "value": ip})
        if public_ips:
            types.append("ip_address")

        return matches, types

    # ================================================================
    # 凭证检测
    # ================================================================

    def _detect_credentials(self, text: str) -> Tuple[List[Dict], List[str]]:
        matches = []
        types = []

        for pattern, cred_type in self.CREDENTIAL_PATTERNS:
            found = pattern.findall(text)
            if found:
                for val in found[:2]:
                    s = val if isinstance(val, str) else str(val)
                    matches.append({"type": cred_type, "value": self._mask(s, 0, 0, show_len=8)})
                if cred_type not in types:
                    types.append(cred_type)

        return matches, types

    # ================================================================
    # 内部配置检测
    # ================================================================

    def _detect_internal_config(self, text: str) -> Tuple[List[Dict], List[str]]:
        matches = []
        types = []

        for pattern, config_type in self.INTERNAL_CONFIG_PATTERNS:
            found = pattern.findall(text)
            if found:
                for val in found[:2]:
                    matches.append({"type": config_type, "value": self._mask(val, 0, 0, show_len=12)})
                if config_type not in types:
                    types.append(config_type)

        return matches, types

    # ================================================================
    # 风险评分
    # ================================================================

    def _calc_risk_score(
        self,
        pii_types: List[str],
        credential_types: List[str],
        config_types: List[str],
    ) -> float:
        score = 0.0

        pii_weights = {
            'phone': 0.15, 'email': 0.1, 'id_card': 0.3, 'ip_address': 0.05,
        }
        for t in pii_types:
            score += pii_weights.get(t, 0.1)

        credential_weights = {
            'api_key': 0.2, 'aws_access_key': 0.25, 'aws_secret': 0.3,
            'jwt_token': 0.15, 'password': 0.2, 'private_key': 0.4,
            'db_connection': 0.35, 'github_token': 0.3,
        }
        for t in credential_types:
            score += credential_weights.get(t, 0.2)

        score += len(config_types) * 0.1

        return min(score, 1.0)

    def _infer_privacy_level(
        self,
        has_pii: bool,
        has_credentials: bool,
        has_internal_config: bool,
        risk_score: float,
    ) -> PrivacyLevel:
        if has_credentials:
            return PrivacyLevel.CRITICAL
        if risk_score >= 0.5:
            return PrivacyLevel.HIGH
        if has_pii:
            return PrivacyLevel.MEDIUM
        if has_internal_config:
            return PrivacyLevel.LOW
        return PrivacyLevel.NONE

    # ================================================================
    # 工具方法
    # ================================================================

    @staticmethod
    def _mask(text: str, keep_start: int = 3, keep_end: int = 4, show_len: int = 0) -> str:
        if show_len > 0:
            return f"{text[:show_len]}..."
        if len(text) <= keep_start + keep_end:
            return text[0] + "*" * (len(text) - 2) + text[-1] if len(text) > 2 else "***"
        return text[:keep_start] + "*" * (len(text) - keep_start - keep_end) + text[-keep_end:]

    @staticmethod
    def _mask_email(email: str) -> str:
        local, domain = email.split('@', 1)
        if len(local) <= 2:
            masked_local = local[0] + "*"
        else:
            masked_local = local[0] + "*" * (len(local) - 2) + local[-1]
        return f"{masked_local}@{domain}"

    @staticmethod
    def _is_private_ip(ip: str) -> bool:
        parts = ip.split('.')
        if len(parts) != 4:
            return False
        try:
            octets = [int(p) for p in parts]
        except ValueError:
            return False
        if octets[0] == 10:
            return True
        if octets[0] == 172 and 16 <= octets[1] <= 31:
            return True
        if octets[0] == 192 and octets[1] == 168:
            return True
        if octets[0] == 127:
            return True
        return False