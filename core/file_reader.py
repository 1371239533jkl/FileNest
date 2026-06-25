"""
文件内容提取器 —— 读取常见文件格式的文本内容。

支持: .txt, .md, .py, .java, .js, .ts, .html, .css, .json, .xml,
       .csv, .tsv, .yaml, .yml, .toml, .ini, .cfg, .log,
       .sql, .sh, .bat, .ps1, .c, .cpp, .h, .hpp, .rs, .go,
       .pdf (需 PyPDF2), .docx (需 python-docx)

对于不支持的类型返回 None。
"""
import os
from typing import Optional

from utils.logger import logger

# 纯文本扩展名（直接读取为 UTF-8）
_TEXT_EXTENSIONS = {
    '.txt', '.md', '.py', '.java', '.js', '.ts', '.jsx', '.tsx',
    '.html', '.htm', '.css', '.scss', '.less',
    '.json', '.xml', '.csv', '.tsv', '.yaml', '.yml', '.toml',
    '.ini', '.cfg', '.conf', '.log',
    '.sql', '.sh', '.bat', '.ps1', '.c', '.cpp', '.h', '.hpp',
    '.rs', '.go', '.rb', '.php', '.swift', '.kt',
    '.env', '.gitignore', '.dockerignore', '.editorconfig',
    '.vue', '.svelte',
}

# 二进制但可提取文本的类型
_PDF_EXT = '.pdf'
_DOCX_EXT = '.docx'

# 最大读取字符数（避免超大文件塞满 prompt）
_MAX_CHARS = 5000


def can_read_content(file_path: str) -> bool:
    """检查文件是否支持内容提取"""
    ext = os.path.splitext(file_path)[1].lower()
    return ext in _TEXT_EXTENSIONS or ext == _PDF_EXT or ext == _DOCX_EXT


def read_file_content(file_path: str, max_chars: int = _MAX_CHARS) -> Optional[str]:
    """读取文件的文本内容。

    Args:
        file_path: 文件绝对路径
        max_chars: 最大返回字符数（超出截断）

    Returns:
        文本内容字符串，或 None（文件不存在/不支持/读取失败）
    """
    if not file_path or not os.path.exists(file_path):
        return None

    ext = os.path.splitext(file_path)[1].lower()

    try:
        # 纯文本
        if ext in _TEXT_EXTENSIONS:
            return _read_text_file(file_path, max_chars)

        # PDF
        if ext == _PDF_EXT:
            return _read_pdf_file(file_path, max_chars)

        # Word
        if ext == _DOCX_EXT:
            return _read_docx_file(file_path, max_chars)

        return None

    except Exception as e:
        logger.debug(f"读取文件内容失败 ({file_path}): {e}")
        return None


def _read_text_file(path: str, max_chars: int) -> Optional[str]:
    """读取纯文本文件"""
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read(max_chars + 100)
        if len(content) > max_chars:
            content = content[:max_chars] + "\n...(内容已截断)"
        return content.strip() or None
    except Exception:
        return None


def _read_pdf_file(path: str, max_chars: int) -> Optional[str]:
    """读取 PDF 文本"""
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(path)
        lines = []
        total = 0
        for page in reader.pages:
            text = page.extract_text()
            if text:
                lines.append(text)
                total += len(text)
                if total >= max_chars:
                    break
        content = "\n".join(lines)
        if len(content) > max_chars:
            content = content[:max_chars] + "\n...(内容已截断)"
        return content.strip() or None
    except ImportError:
        logger.debug("PyPDF2 未安装，跳过 PDF 内容提取")
        return None
    except Exception as e:
        logger.debug(f"PDF 读取失败: {e}")
        return None


def _read_docx_file(path: str, max_chars: int) -> Optional[str]:
    """读取 Word 文档文本"""
    try:
        from docx import Document
        doc = Document(path)
        lines = []
        total = 0
        for para in doc.paragraphs:
            if para.text.strip():
                lines.append(para.text)
                total += len(para.text)
                if total >= max_chars:
                    break
        content = "\n".join(lines)
        if len(content) > max_chars:
            content = content[:max_chars] + "\n...(内容已截断)"
        return content.strip() or None
    except ImportError:
        logger.debug("python-docx 未安装，跳过 Word 内容提取")
        return None
    except Exception as e:
        logger.debug(f"Word 读取失败: {e}")
        return None
