"""
AI 响应解析器 —— 从 LLM 输出中提取结构化 JSON 和纯文本。
"""

import json
import re
from typing import Optional

from utils.logger import logger


class ResponseParser:
    """从 LLM 文本响应中提取并校验结构化数据"""

    @staticmethod
    def extract_json(text: str) -> Optional[dict]:
        """从 LLM 输出中提取 JSON 对象。

        按以下策略依次尝试：
        1. 整段文本直接 json.loads
        2. 提取 ```json ... ``` 代码块
        3. 提取首个 { ... } 块（贪婪匹配）
        4. 修复尾部截断的 JSON
        """
        if not text:
            return None

        # 策略 1: 直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 策略 2: 提取 markdown code fence
        m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except json.JSONDecodeError:
                pass

        # 策略 3: 提取最外层 { ... }
        start = text.find('{')
        if start == -1:
            return None

        depth = 0
        for i in range(start, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    candidate = text[start:i+1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        fixed = ResponseParser._fix_truncated(candidate)
                        if fixed:
                            try:
                                return json.loads(fixed)
                            except json.JSONDecodeError:
                                pass
                    return None
        return None

    @staticmethod
    def _fix_truncated(json_str: str) -> Optional[str]:
        """尝试修复因 max_tokens 截断导致的不完整 JSON"""
        open_braces = json_str.count('{') - json_str.count('}')
        open_brackets = json_str.count('[') - json_str.count(']')

        if open_braces == 0 and open_brackets == 0:
            return None

        last_comma = json_str.rfind(',')
        if last_comma > 0:
            json_str = json_str[:last_comma]

        json_str += ']' * open_brackets
        json_str += '}' * open_braces
        return json_str

    # ── 纯文本解析（新增） ──

    @staticmethod
    def extract_plain_text(text: str) -> str:
        """提取 LLM 输出的纯文本，自动去除 JSON 代码块和 markdown 标记。

        用于摘要、问答、文件描述等非结构化输出场景。
        """
        if not text:
            return ""

        # 移除 markdown JSON 代码块
        text = re.sub(r'```(?:json)?\s*\n?.*?\n?```', '', text, flags=re.DOTALL)

        # 移除残留的 JSON 对象字符串
        text = re.sub(r'\{[^{}]*\}', '', text)

        # 清理多余空行
        text = re.sub(r'\n{3,}', '\n\n', text)

        return text.strip()

    # ── 结构化解析 ──

    @classmethod
    def parse_search(cls, text: str) -> Optional[dict]:
        """解析搜索 LLM 响应"""
        data = cls.extract_json(text)
        if not data:
            logger.warning("搜索解析失败: 无法提取 JSON")
            return None

        result = {}
        field_map = {
            'name': str, 'file_type': str,
            'min_size': int, 'max_size': int,
            'start_date': str, 'end_date': str,
            'is_duplicate': int, 'explanation': str,
        }
        for key, typ in field_map.items():
            val = data.get(key)
            if val is None or val == 'null':
                result[key] = None
            elif key in ('min_size', 'max_size', 'is_duplicate'):
                try:
                    result[key] = int(val)
                except (ValueError, TypeError):
                    result[key] = None
            else:
                result[key] = str(val) if val else None

        result['_explanation'] = data.get('explanation', '')
        return result

    @classmethod
    def parse_tags(cls, text: str) -> Optional[list]:
        """解析标签推荐 LLM 响应 → [(tag_name, confidence), ...]"""
        data = cls.extract_json(text)
        if not data:
            logger.warning("标签解析失败: 无法提取 JSON")
            return None

        tags = data.get('tags', [])
        if not isinstance(tags, list):
            return None

        result = []
        for t in tags:
            if not isinstance(t, dict):
                continue
            name = t.get('name', '').strip()
            if not name:
                continue
            try:
                conf = float(t.get('confidence', 0.5))
            except (ValueError, TypeError):
                conf = 0.5
            result.append((name, min(1.0, max(0.0, conf))))

        return result[:8]
