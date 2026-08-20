"""
代码检测特征提取器
从消息文本中识别代码块、语言、结构特征
纯规则匹配（正则 + 关键词），无外部依赖
"""
import re
from typing import List
from src.core.schemas.request import Message
from src.core.schemas.task import CodeFeatures


class CodeDetector:
    """代码检测特征提取器"""

    # Markdown 代码块：```language\n...\n```
    CODE_BLOCK_PATTERN = re.compile(
        r'```(\w*)\s*\n(.*?)```',
        re.DOTALL
    )

    # 行内代码：`code`
    INLINE_CODE_PATTERN = re.compile(r'`([^`]+?)`')

    # 常见编程语言关键词映射（文件扩展名 → 语言名）
    LANGUAGE_ALIASES = {
        'py': 'python', 'python': 'python', 'py3': 'python',
        'js': 'javascript', 'javascript': 'javascript', 'ts': 'typescript',
        'typescript': 'typescript',
        'java': 'java',
        'go': 'go', 'golang': 'go',
        'rs': 'rust', 'rust': 'rust',
        'cpp': 'cpp', 'c++': 'cpp', 'c': 'c',
        'cs': 'csharp', 'c#': 'csharp', 'csharp': 'csharp',
        'rb': 'ruby', 'ruby': 'ruby',
        'php': 'php',
        'swift': 'swift',
        'kt': 'kotlin', 'kotlin': 'kotlin',
        'sh': 'bash', 'bash': 'bash', 'shell': 'bash',
        'sql': 'sql',
        'html': 'html', 'htm': 'html',
        'css': 'css',
        'json': 'json',
        'yaml': 'yaml', 'yml': 'yaml',
        'xml': 'xml',
        'md': 'markdown', 'markdown': 'markdown',
        'dockerfile': 'dockerfile',
    }

    # import 语句特征
    IMPORT_PATTERNS = {
        'python': re.compile(
            r'^\s*(?:import\s+\w+|from\s+\w+\s+import\s+)', re.MULTILINE
        ),
        'javascript': re.compile(
            r'^\s*(?:import\s+.*?from\s+[\'"]|require\s*\([\'"].*?[\'"]\))', re.MULTILINE
        ),
        'java': re.compile(
            r'^\s*import\s+[\w.]+', re.MULTILINE
        ),
        'go': re.compile(
            r'^\s*import\s+(?:\w+\s+)?["\']', re.MULTILINE
        ),
        'rust': re.compile(
            r'^\s*use\s+[\w:]+', re.MULTILINE
        ),
    }

    # 函数定义特征
    FUNCTION_PATTERNS = {
        'python': re.compile(r'^\s*def\s+\w+\s*\(', re.MULTILINE),
        'javascript': re.compile(
            r'^\s*(?:function\s+\w+|const\s+\w+\s*=\s*(?:\([^)]*\)|function)\s*[=>({])',
            re.MULTILINE
        ),
        'go': re.compile(r'^\s*func\s+(?:\(\w+\s+\*?\w+\)\s+)?\w+\s*\(', re.MULTILINE),
        'rust': re.compile(r'^\s*(?:pub\s+)?fn\s+\w+[<(]', re.MULTILINE),
        'java': re.compile(
            r'^\s*(?:public|private|protected|static|\s)+[\w<>\[\]]+\s+\w+\s*\([^)]*\)\s*\{?',
            re.MULTILINE
        ),
    }

    # 类定义特征
    CLASS_PATTERNS = {
        'python': re.compile(r'^\s*class\s+\w+[\s(:]', re.MULTILINE),
        'javascript': re.compile(r'^\s*class\s+\w+[\s{]', re.MULTILINE),
        'java': re.compile(r'^\s*(?:public\s+)?class\s+\w+[\s{]', re.MULTILINE),
        'go': re.compile(r'^\s*type\s+\w+\s+struct\s*\{', re.MULTILINE),
        'rust': re.compile(r'^\s*(?:pub\s+)?struct\s+\w+[\s{]', re.MULTILINE),
    }

    # ================================================================
    # 主入口
    # ================================================================

    def extract(self, messages: List[Message]) -> CodeFeatures:
        """
        从消息列表提取代码特征

        Args:
            messages: 对话消息列表

        Returns:
            CodeFeatures: 代码相关特征
        """
        # 合并所有消息文本
        full_text = "\n".join(m.content for m in messages if m.content)

        # 1. 提取代码块
        code_blocks = self._extract_code_blocks(full_text)

        # 2. 提取行内代码
        inline_codes = self.INLINE_CODE_PATTERN.findall(full_text)

        # 3. 汇总
        all_languages = []
        total_code_lines = 0
        for lang, code in code_blocks:
            normalized = self._normalize_language(lang)
            if normalized and normalized not in all_languages:
                all_languages.append(normalized)
            total_code_lines += code.count('\n') + 1

        has_code = len(code_blocks) > 0 or len(inline_codes) > 0

        # 4. 结构特征（针对最可能的语言检测）
        primary_lang = all_languages[0] if all_languages else None
        has_imports = self._has_imports(full_text, primary_lang)
        has_functions = self._has_functions(full_text, primary_lang)
        has_classes = self._has_classes(full_text, primary_lang)

        # 多文件检测（启发式：提及多个文件名）
        has_multiple_files = self._detect_multiple_files(full_text)

        return CodeFeatures(
            has_code=has_code,
            code_languages=all_languages,
            code_block_count=len(code_blocks),
            total_code_lines=total_code_lines,
            has_multiple_files=has_multiple_files,
            has_imports=has_imports,
            has_functions=has_functions,
            has_classes=has_classes,
        )

    # ================================================================
    # 代码块提取
    # ================================================================

    def _extract_code_blocks(self, text: str) -> List[tuple]:
        """
        提取所有 Markdown 代码块

        Returns:
            List[tuple]: [(language, code_content), ...]
        """
        matches = self.CODE_BLOCK_PATTERN.findall(text)
        return [(lang.strip().lower(), code.strip()) for lang, code in matches]

    def _normalize_language(self, lang: str) -> str:
        """将语言标识符标准化为统一名称"""
        if not lang:
            return ""
        lang = lang.lower().strip()
        return self.LANGUAGE_ALIASES.get(lang, lang)

    # ================================================================
    # 结构特征检测
    # ================================================================

    def _has_imports(self, text: str, primary_lang: str = None) -> bool:
        """检测是否包含 import / include 语句"""
        if primary_lang and primary_lang in self.IMPORT_PATTERNS:
            return bool(self.IMPORT_PATTERNS[primary_lang].search(text))
        # 通用回退：检查常见 import 关键字
        generic_import = re.compile(
            r'^\s*(?:import\s+|from\s+\w+\s+import\s+|require\s*\(|#include\s*)',
            re.MULTILINE
        )
        return bool(generic_import.search(text))

    def _has_functions(self, text: str, primary_lang: str = None) -> bool:
        """检测是否包含函数定义"""
        if primary_lang and primary_lang in self.FUNCTION_PATTERNS:
            return bool(self.FUNCTION_PATTERNS[primary_lang].search(text))
        # 通用回退
        generic_func = re.compile(
            r'^\s*(?:def\s+|function\s+|func\s+|fn\s+|sub\s+)',
            re.MULTILINE
        )
        return bool(generic_func.search(text))

    def _has_classes(self, text: str, primary_lang: str = None) -> bool:
        """检测是否包含类 / 结构体定义"""
        if primary_lang and primary_lang in self.CLASS_PATTERNS:
            return bool(self.CLASS_PATTERNS[primary_lang].search(text))
        # 通用回退
        generic_class = re.compile(
            r'^\s*(?:class\s+|struct\s+|interface\s+|trait\s+)',
            re.MULTILINE
        )
        return bool(generic_class.search(text))

    def _detect_multiple_files(self, text: str) -> bool:
        """启发式检测是否涉及多文件"""
        # 模式1：文件名列表（如 file1.py, file2.py）
        file_pattern = re.compile(
            r'\b\w+\.(?:py|js|ts|java|go|rs|cpp|c|h|rb|php|swift)\b',
            re.IGNORECASE
        )
        files = set(f.lower() for f in file_pattern.findall(text))
        if len(files) >= 2:
            return True

        # 模式2：提及多文件关键词
        multi_file_keywords = [
            '多个文件', 'multi-file', 'multi file',
            '目录结构', 'directory', '文件夹',
            '重构', 'refactor', '拆分', 'split',
            '模块化', 'modular',
        ]
        text_lower = text.lower()
        if any(kw in text_lower for kw in multi_file_keywords):
            return True

        return False