"""
AI 预处理层 —— 输入清洗、安全过滤、输出校验。
"""

import re
from utils.logger import logger

# ── 注入攻击检测 ──
_INJECTION_PATTERNS = [
    r'ignore\s+(all\s+)?previous\s+(instructions?|prompts?)',
    r'you\s+are\s+now\s+(DAN|jailbreak|evil|unrestricted)',
    r'\[INST\].*\[/INST\]',
    r'<\|im_start\|>',
    r'<\|im_end\|>',
    r'system:\s*(override|bypass|ignore)',
]

# ── 输出危险内容检测 ──
_DANGEROUS_OUTPUT = [
    r'rm\s+-rf\s+/',
    r'format\s+[cC]:',
    r'(DROP|TRUNCATE|ALTER)\s+(TABLE|DATABASE)',
    r'os\.system\s*\(',
    r'eval\s*\(',
    r'__import__\s*\(',
]


class Preprocessor:
    """输入预处理：清洗 + 安全检测"""

    @staticmethod
    def clean(text: str) -> str:
        """基础文本清洗"""
        if not text or not isinstance(text, str):
            return ""
        # 去首尾空白，规范化换行
        text = text.strip()
        text = re.sub(r'\r\n|\r', '\n', text)
        # 压缩连续空白（保留换行）
        text = re.sub(r'[ \t]+', ' ', text)
        return text

    @staticmethod
    def is_simple(query: str) -> bool:
        """判断查询是否足够简单，可以直接走规则引擎"""
        query = (query or '').strip().lower()
        # 简单关键词查询：少于 5 个字，或纯数字，或明显单维度查询
        if len(query) <= 5:
            return True
        # 纯文件名查询
        if re.match(r'^[\w.\-]+$', query):
            return True
        return False

    @classmethod
    def check_safety(cls, text: str) -> tuple[bool, str]:
        """检查输入安全性。返回 (通过, 原因)"""
        for pattern in _INJECTION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                logger.warning(f"检测到注入攻击: {pattern}")
                return False, "检测到不安全的输入"
        return True, ""


class OutputValidator:
    """输出校验：结构合法性 + 安全性"""

    @staticmethod
    def check_dangerous(text: str) -> tuple[bool, str]:
        """检查 LLM 输出是否包含危险命令"""
        for pattern in _DANGEROUS_OUTPUT:
            if re.search(pattern, text, re.IGNORECASE):
                logger.warning(f"LLM 输出含危险内容: {pattern}")
                return False, "输出包含不安全内容"
        return True, ""

    @staticmethod
    def validate_search_params(params: dict) -> tuple[bool, list[str]]:
        """校验搜索参数的合法性"""
        errors = []
        valid_types = {'image', 'document', 'code', 'video',
                       'audio', 'archive', 'executable', 'font'}
        if params.get('file_type') and params['file_type'] not in valid_types:
            errors.append(f"无效的文件类型: {params['file_type']}")
        if params.get('min_size') is not None and params['min_size'] < 0:
            errors.append("最小大小不能为负")
        if params.get('max_size') is not None and params['max_size'] < 0:
            errors.append("最大大小不能为负")
        return len(errors) == 0, errors
