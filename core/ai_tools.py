"""
AI 工具注册与执行系统 —— 让 LLM 自主调度多种工具完成复杂任务。

支持的预设工具：
- search_files  : 检索本地文件数据库（保留原有能力）
- search_web    : 联网搜索，获取实时信息
- read_file     : 读取本地文件内容
- execute_python: 受限沙箱执行 Python 代码

用法：
    registry = ToolRegistry()
    registry.register(search_files_tool)
    schemas = registry.get_tool_schemas()  # 传给 LLM 的 tools 参数
    result = registry.execute("search_web", {"query": "Python 3.13"})
"""

import json
import os
import subprocess
import tempfile
import re
from typing import Optional, Callable, Any
from dataclasses import dataclass, field

import httpx

from utils.logger import logger


# ══════════════════════════════════════════════════════════════════════════════
# 工具定义
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ToolDefinition:
    """单个工具定义"""
    name: str                              # 工具名，如 "search_files"
    description: str                       # LLM 可读的功能描述
    parameters: dict                       # JSON Schema 格式的参数定义
    handler: Callable[..., str]            # 执行函数，接收 **kwargs，返回文本结果
    requires_db: bool = False              # 是否需要数据库连接
    db_manager: Any = None                 # 数据库管理器实例（延迟注入）

    def execute(self, arguments: dict) -> str:
        """执行工具并返回文本结果"""
        try:
            result = self.handler(**(arguments or {}))
            # 截断过长结果，避免撑爆上下文
            if isinstance(result, str) and len(result) > 8000:
                result = result[:8000] + "\n...(结果已截断)"
            return result
        except Exception as e:
            logger.error(f"工具 {self.name} 执行失败: {e}")
            return f"[工具执行错误] {self.name}: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# 工具注册表
# ══════════════════════════════════════════════════════════════════════════════

class ToolRegistry:
    """工具注册与调度中心"""

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """注册一个工具"""
        self._tools[tool.name] = tool
        logger.debug(f"工具已注册: {tool.name}")

    def unregister(self, name: str) -> None:
        """注销一个工具"""
        self._tools.pop(name, None)

    def get(self, name: str) -> Optional[ToolDefinition]:
        """获取指定工具"""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """列出所有已注册工具名"""
        return list(self._tools.keys())

    def get_tool_schemas(self) -> list[dict]:
        """生成 OpenAI 兼容的 tools 参数列表（仅描述，不含 handler）"""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                }
            }
            for t in self._tools.values()
        ]

    def execute(self, tool_name: str, arguments: dict) -> str:
        """执行指定工具并返回文本结果"""
        tool = self._tools.get(tool_name)
        if not tool:
            return f"[错误] 未知工具: {tool_name}，可用工具: {', '.join(self.list_tools())}"
        return tool.execute(arguments)


# ══════════════════════════════════════════════════════════════════════════════
# 预设工具：文件搜索
# ══════════════════════════════════════════════════════════════════════════════

def _search_files_handler(query: str, file_type: str = None,
                          max_results: int = 20, _db=None, _ai_layer=None) -> str:
    """搜索本地文件数据库"""
    if _db is None:
        return "[错误] 文件搜索工具未连接数据库"

    try:
        sql = "SELECT file_name, file_path, file_type, file_size, modify_time FROM files WHERE 1=1"
        params = []

        # 关键词搜索（文件名或路径模糊匹配）
        keywords = re.split(r'[\s\|,，、]+', query.strip()) if query.strip() else []
        if keywords:
            like_clauses = []
            for kw in keywords[:5]:  # 最多 5 个关键词
                kw = kw.strip()
                if kw:
                    like_clauses.append("(file_name LIKE %s OR file_path LIKE %s)")
                    params.extend([f"%{kw}%", f"%{kw}%"])
            if like_clauses:
                sql += " AND (" + " OR ".join(like_clauses) + ")"

        # 文件类型过滤
        if file_type:
            sql += " AND file_type = %s"
            params.append(file_type)

        sql += " ORDER BY modify_time DESC LIMIT %s"
        params.append(max_results)

        rows = _db.execute_query(sql, tuple(params))

        if not rows:
            return f"未找到与 '{query}' 相关的文件。"

        lines = [f"找到 {len(rows)} 个相关文件（搜索词: {query}）:"]
        for r in rows:
            size_str = _format_bytes(r.get('file_size', 0))
            lines.append(
                f"- {r['file_name']} ({size_str}) "
                f"类型:{r.get('file_type','unknown')} "
                f"路径:{r['file_path']}"
            )
        return "\n".join(lines)

    except Exception as e:
        return f"[文件搜索错误] {e}"


_search_files_schema = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "搜索关键词，多个关键词用空格或逗号分隔"
        },
        "file_type": {
            "type": "string",
            "enum": ["image", "document", "code", "video", "audio", "archive", "executable", "font", "other"],
            "description": "可选的文件类型过滤"
        },
        "max_results": {
            "type": "integer",
            "description": "最大返回条数，默认 20",
            "default": 20
        }
    },
    "required": ["query"]
}


def create_search_files_tool(db_manager=None, ai_layer=None) -> ToolDefinition:
    """创建文件搜索工具（注入数据库依赖）"""
    def handler(**kwargs):
        return _search_files_handler(**kwargs, _db=db_manager, _ai_layer=ai_layer)
    return ToolDefinition(
        name="search_files",
        description="搜索本地文件数据库。当你需要查找用户电脑上的文件时使用此工具。支持按文件名、路径关键词搜索，可按文件类型过滤。",
        parameters=_search_files_schema,
        handler=handler,
        requires_db=True,
        db_manager=db_manager,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 预设工具：联网搜索
# ══════════════════════════════════════════════════════════════════════════════

_WEB_SEARCH_CLIENT: Optional[httpx.Client] = None


def _get_web_client() -> httpx.Client:
    global _WEB_SEARCH_CLIENT
    if _WEB_SEARCH_CLIENT is None:
        _WEB_SEARCH_CLIENT = httpx.Client(
            timeout=httpx.Timeout(15.0),
            headers={"User-Agent": "SmartFileManager/2.0 (AI Assistant)"},
            follow_redirects=True,
        )
    return _WEB_SEARCH_CLIENT


def _search_web_handler(query: str, max_results: int = 5) -> str:
    """联网搜索（使用 DuckDuckGo HTML 接口，免费无需 API key）"""
    try:
        client = _get_web_client()

        # 使用 DuckDuckGo Lite 的 HTML 版本（更稳定）
        resp = client.post(
            "https://lite.duckduckgo.com/lite/",
            data={"q": query, "kl": "wt-wt"},
        )

        if resp.status_code != 200:
            # 回退：尝试 DuckDuckGo Instant Answer API
            resp2 = client.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            )
            if resp2.status_code == 200:
                data = resp2.json()
                results = []
                if data.get("AbstractText"):
                    results.append(f"摘要: {data['AbstractText']}")
                if data.get("RelatedTopics"):
                    for topic in data["RelatedTopics"][:max_results]:
                        if isinstance(topic, dict) and topic.get("Text"):
                            results.append(f"- {topic['Text']}")
                if results:
                    return "\n".join(results)

            return f"[联网搜索] 搜索 '{query}' 未获取到结果 (HTTP {resp.status_code})"

        # 解析 DuckDuckGo Lite HTML 结果
        from html.parser import HTMLParser

        class ResultParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.results = []
                self._in_link = False
                self._in_snippet = False
                self._current_title = ""
                self._current_link = ""
                self._current_snippet = ""
                self._row_count = 0

            def handle_starttag(self, tag, attrs):
                attrs_dict = dict(attrs)
                if tag == "a" and "class" in attrs_dict and "result-link" in attrs_dict.get("class", ""):
                    self._in_link = True
                    self._current_link = attrs_dict.get("href", "")
                elif tag == "td" and "class" in attrs_dict and "result-snippet" in attrs_dict.get("class", ""):
                    self._in_snippet = True

            def handle_endtag(self, tag):
                if tag == "a" and self._in_link:
                    self._in_link = False
                    self._row_count += 1
                elif tag == "td" and self._in_snippet:
                    self._in_snippet = False
                    if self._current_title or self._current_snippet:
                        self.results.append({
                            "title": self._current_title.strip(),
                            "link": self._current_link.strip(),
                            "snippet": self._current_snippet.strip(),
                        })
                        self._current_title = ""
                        self._current_link = ""
                        self._current_snippet = ""
                        self._row_count = 0

            def handle_data(self, data):
                if self._in_link:
                    self._current_title += data
                elif self._in_snippet:
                    self._current_snippet += data

        parser = ResultParser()
        parser.feed(resp.text)

        # 如果正则解析不到，尝试简单提取链接
        if not parser.results:
            link_pattern = re.findall(
                r'<a[^>]*href="(https?://[^"]+)"[^>]*class="[^"]*result-link[^"]*"[^>]*>(.*?)</a>',
                resp.text, re.DOTALL
            )
            snippet_pattern = re.findall(
                r'<td[^>]*class="[^"]*result-snippet[^"]*"[^>]*>(.*?)</td>',
                resp.text, re.DOTALL
            )
            for i, (link, title) in enumerate(link_pattern[:max_results]):
                title_clean = re.sub(r'<[^>]+>', '', title).strip()
                snippet_clean = ""
                if i < len(snippet_pattern):
                    snippet_clean = re.sub(r'<[^>]+>', '', snippet_pattern[i]).strip()
                parser.results.append({
                    "title": title_clean,
                    "link": link,
                    "snippet": snippet_clean,
                })

        if not parser.results:
            return f"搜索 '{query}' 未找到网页结果。"

        lines = [f"网页搜索 '{query}' 的结果:"]
        for i, r in enumerate(parser.results[:max_results], 1):
            lines.append(f"{i}. {r['title']}")
            if r['snippet']:
                lines.append(f"   {r['snippet'][:200]}")
            lines.append(f"   链接: {r['link']}")

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"联网搜索失败: {e}")
        return f"[联网搜索错误] {e}。可尝试用其他搜索词重试。"


_search_web_schema = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "搜索查询词"
        },
        "max_results": {
            "type": "integer",
            "description": "最大返回条数，默认 5",
            "default": 5
        }
    },
    "required": ["query"]
}


def create_search_web_tool() -> ToolDefinition:
    """创建联网搜索工具"""
    return ToolDefinition(
        name="search_web",
        description="联网搜索互联网信息。当你需要获取实时信息、最新资讯、技术文档、行业动态等本地文件之外的知识时使用。",
        parameters=_search_web_schema,
        handler=_search_web_handler,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 预设工具：读取本地文件
# ══════════════════════════════════════════════════════════════════════════════

def _read_file_handler(file_path: str, max_chars: int = 3000) -> str:
    """读取本地文件内容"""
    # 安全检查：禁止读取系统敏感文件
    dangerous_patterns = [
        r'(^|[/\\])\.env$', r'/etc/(passwd|shadow)', r'\\Windows\\System32\\',
        r'\.pem$', r'\.key$', r'id_rsa', r'known_hosts',
    ]
    for pattern in dangerous_patterns:
        if re.search(pattern, file_path, re.IGNORECASE):
            return f"[安全限制] 拒绝读取敏感文件: {file_path}"

    if not os.path.exists(file_path):
        return f"[错误] 文件不存在: {file_path}"

    if not os.path.isfile(file_path):
        return f"[错误] 不是文件: {file_path}"

    file_size = os.path.getsize(file_path)
    if file_size > 10 * 1024 * 1024:  # 超过 10MB 拒绝读取
        return f"[跳过] 文件过大 ({_format_bytes(file_size)})，拒绝读取内容"

    # 检查是否为文本文件
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(max_chars)
    except Exception as e:
        return f"[读取错误] 无法读取文件 {file_path}: {e}"

    truncated = " ...(内容已截断)" if len(content) >= max_chars else ""
    ext = os.path.splitext(file_path)[1].lower()
    lang = ext.lstrip(".") if ext else "text"

    return f"文件: {os.path.basename(file_path)} ({_format_bytes(file_size)}):\n```{lang}\n{content}{truncated}\n```"


_read_file_schema = {
    "type": "object",
    "properties": {
        "file_path": {
            "type": "string",
            "description": "要读取的文件的完整路径"
        },
        "max_chars": {
            "type": "integer",
            "description": "最大返回字符数，默认 3000",
            "default": 3000
        }
    },
    "required": ["file_path"]
}


def create_read_file_tool() -> ToolDefinition:
    """创建文件读取工具"""
    return ToolDefinition(
        name="read_file",
        description="读取本地文件内容。当你需要查看文件具体内容时使用。支持代码、文档、配置文件等文本文件。注意：只能读取文本文件。",
        parameters=_read_file_schema,
        handler=_read_file_handler,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 预设工具：Python 代码执行
# ══════════════════════════════════════════════════════════════════════════════

# 危险模块黑名单
_FORBIDDEN_MODULES = {
    "os", "subprocess", "sys", "shutil", "socket", "requests",
    "httpx", "urllib", "http", "ftplib", "smtplib", "telnetlib",
    "pickle", "marshal", "ctypes", "multiprocessing", "threading",
    "signal", "pty", "fcntl", "posix", "grp", "pwd", "spwd",
    "crypt", "ssl", "hashlib",
}


def _execute_python_handler(code: str, timeout: int = 10) -> str:
    """在受限沙箱中执行 Python 代码"""
    # 基础安全检查
    code_lower = code.lower()
    for mod in _FORBIDDEN_MODULES:
        if f"import {mod}" in code_lower or f"from {mod}" in code_lower:
            return f"[安全限制] 代码包含禁止模块: {mod}"

    if "open(" in code and ("/etc/" in code or "C:\\Windows" in code):
        return "[安全限制] 代码尝试访问系统目录"

    # 写入临时文件执行
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            tmp_path = f.name

        result = subprocess.run(
            ["python", tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=tempfile.gettempdir(),
        )

        output_parts = []
        if result.stdout:
            output_parts.append(f"[标准输出]\n{result.stdout.strip()}")
        if result.stderr:
            output_parts.append(f"[标准错误]\n{result.stderr.strip()}")
        if not output_parts:
            output_parts.append("[执行完毕，无输出]")

        return "\n".join(output_parts)

    except subprocess.TimeoutExpired:
        return f"[超时] 代码执行超过 {timeout} 秒，已终止"
    except Exception as e:
        return f"[执行错误] {e}"
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


_execute_python_schema = {
    "type": "object",
    "properties": {
        "code": {
            "type": "string",
            "description": "要执行的 Python 代码。安全限制：禁止 import os/sys/subprocess/socket 等危险模块。"
        },
        "timeout": {
            "type": "integer",
            "description": "超时秒数，默认 10",
            "default": 10
        }
    },
    "required": ["code"]
}


def create_execute_python_tool() -> ToolDefinition:
    """创建 Python 代码执行工具"""
    return ToolDefinition(
        name="execute_python",
        description="在安全的沙箱环境中执行 Python 代码。适合做数据计算、格式转换、文本处理等简单任务。注意：禁止访问文件系统、网络和系统模块。",
        parameters=_execute_python_schema,
        handler=_execute_python_handler,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════════════════════════════════════════

def _format_bytes(size: int) -> str:
    """格式化字节数为人类可读"""
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    else:
        return f"{size / (1024 * 1024 * 1024):.1f} GB"


def create_default_registry(db_manager=None, ai_layer=None) -> ToolRegistry:
    """创建包含所有预设工具的注册表"""
    registry = ToolRegistry()
    registry.register(create_search_files_tool(db_manager=db_manager, ai_layer=ai_layer))
    registry.register(create_search_web_tool())
    registry.register(create_read_file_tool())
    registry.register(create_execute_python_tool())
    return registry
