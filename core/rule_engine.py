"""
本地规则引擎 —— 零外部依赖，纯启发式规则。

三层功能：
  NLSearchParser  自然语言搜索解析，将中文/英文查询转为结构化搜索参数
  TagRecommender  基于文件名/路径/类型/大小的智能标签推荐
  CleanupAdvisor  文件清理建议（重复/过期/临时/空白/孤立文件）

所有解析均依赖内置字符串匹配和正则，不联网、不调 LLM。
"""

import re
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple, Any

from config import FILE_TYPES, FILE_TYPE_NAMES
from utils.logger import logger
from utils.display_utils import format_size


# ══════════════════════════════════════════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════════════════════════════════════════

def _strip_unit(value_str: str) -> Tuple[float, str]:
    """从大小字符串中提取数值和单位，如 '100MB' -> (100.0, 'MB')"""
    m = re.match(r'([\d.]+)\s*(KB|MB|GB|TB|kb|mb|gb|tb|K|M|G|T)?', value_str.strip())
    if not m:
        return 0.0, ''
    num = float(m.group(1))
    unit = (m.group(2) or '').upper()
    return num, unit


def _to_bytes(num: float, unit: str) -> int:
    """将数值和单位转为字节数"""
    multipliers = {'KB': 1024, 'MB': 1024 ** 2, 'GB': 1024 ** 3, 'TB': 1024 ** 4,
                   'K': 1024, 'M': 1024 ** 2, 'G': 1024 ** 3, 'T': 1024 ** 4}
    return int(num * multipliers.get(unit, 1))


# ══════════════════════════════════════════════════════════════════════════════
# 1. NL 搜索解析器
# ══════════════════════════════════════════════════════════════════════════════

class NLSearchParser:
    """将自然语言查询解析为 FileDAO.search() 参数。

    支持中英文混合输入，示例：
      "大于100MB的图片"          -> type=image, min_size=100MB
      "上周修改的PDF文档"        -> type=document, ext=.pdf, date range
      "report合同 大文件"        -> name keywords, large files
      "桌面上的重复文件"          -> path contains 桌面, is_duplicate=1
      "最近30天的代码"           -> type=code, date range (last 30 days)
      "videos larger than 500MB" -> type=video, min_size=500MB
    """

    # ── 时间表达式模式 (正则) ──
    _TIME_PATTERNS: List[Tuple[str, str]] = [
        # 相对时间
        (r'今天|today', 'today'),
        (r'昨天|yesterday', 'yesterday'),
        (r'本周|这周|this\s*week', 'this_week'),
        (r'上周|last\s*week', 'last_week'),
        (r'本月|这个月|this\s*month', 'this_month'),
        (r'上月|上个月|last\s*month', 'last_month'),
        (r'今年|this\s*year', 'this_year'),
        (r'去年|last\s*year', 'last_year'),
        # 最近 N 天/周/月
        (r'最近\s*(\d+)\s*天|last\s*(\d+)\s*days?', 'last_n_days'),
        (r'最近\s*(\d+)\s*周|last\s*(\d+)\s*weeks?', 'last_n_weeks'),
        (r'最近\s*(\d+)\s*(个)?月|last\s*(\d+)\s*months?', 'last_n_months'),
        # 指定月份
        (r'(\d{4})\s*年\s*(\d{1,2})\s*月', 'specific_month'),
        (r'(\d{1,2})月(份)?', 'this_year_month'),
        (r'january|february|march|april|may|june|july|august|september|october|november|december',
         'en_month'),
    ]

    # ── 大小表达式（\s* 用贪婪模式，确保捕获数字+单位整体） ──
    _SIZE_PATTERNS: List[Tuple[str, str]] = [
        (r'(?:大于|超过|至少|more\s*than|larger\s*than|at\s*least|>=)\s*([\d.]+\s*(?:KB|MB|GB|TB|K|M|G|T)?)', 'gt'),
        (r'(?:小于|不到|最多|less\s*than|smaller\s*than|at\s*most|<=)\s*([\d.]+\s*(?:KB|MB|GB|TB|K|M|G|T)?)', 'lt'),
        (r'(?:约|大约|about|around|~)\s*([\d.]+\s*(?:KB|MB|GB|TB|K|M|G|T)?)', 'around'),
        (r'(?:大小\s*[:：]?\s*)?([\d.]+\s*(?:KB|MB|GB|TB|K|M|G|T))', 'exact'),
    ]

    # ── 文件类型关键词 (双向映射) ──
    _TYPE_KEYWORDS: Dict[str, str] = {}
    for _ft_key, _ft_cn in FILE_TYPE_NAMES.items():
        if _ft_key == 'other':
            continue
        _TYPE_KEYWORDS[_ft_cn] = _ft_key
    _TYPE_KEYWORDS.update({
        'image': 'image', 'images': 'image', '图片': 'image', '照片': 'image', 'photo': 'image', 'photos': 'image',
        'document': 'document', 'documents': 'document', '文档': 'document', 'doc': 'document',
        'code': 'code', 'codes': 'code', '代码': 'code', '源码': 'code', 'source': 'code',
        'video': 'video', 'videos': 'video', '视频': 'video', 'movie': 'video',
        'audio': 'audio', 'audios': 'audio', '音频': 'audio', '音乐': 'audio', 'music': 'audio',
        'archive': 'archive', 'archives': 'archive', '压缩包': 'archive', '压缩': 'archive', '包': 'archive',
        'executable': 'executable', '可执行文件': 'executable', '程序': 'executable', 'exe': 'executable',
        'font': 'font', 'fonts': 'font', '字体': 'font',
    })

    # ── 文件扩展名关键词 ──
    _EXT_KEYWORDS: Dict[str, str] = {
        'pdf': '.pdf', 'word': '.doc', 'docx': '.docx', 'excel': '.xls', 'xlsx': '.xlsx',
        'ppt': '.ppt', 'pptx': '.pptx', 'txt': '.txt', 'csv': '.csv', 'md': '.md',
        'py': '.py', 'python': '.py', 'js': '.js', 'javascript': '.js', 'ts': '.ts',
        'java': '.java', 'cpp': '.cpp', 'c++': '.cpp', 'go': '.go', 'rust': '.rs',
        'html': '.html', 'css': '.css', 'json': '.json', 'xml': '.xml', 'yaml': '.yml',
        'mp4': '.mp4', 'avi': '.avi', 'mkv': '.mkv', 'mov': '.mov',
        'mp3': '.mp3', 'flac': '.flac', 'wav': '.wav',
        'zip': '.zip', 'rar': '.rar', '7z': '.7z',
        'jpg': '.jpg', 'jpeg': '.jpeg', 'png': '.png', 'gif': '.gif',
    }

    # ── 中日韩字符检测（用于构建兼容中英文的关键词边界） ──
    _CJK_RE = re.compile(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]')

    @classmethod
    def _kw_pattern(cls, keyword: str) -> str:
        """为关键词生成兼容中英文的边界正则。

        中文无 \b 边界，改用：前一个字符不能是关键词的首字，后一个字符不能是关键词的尾字。
        ASCII 关键词仍使用 \b。
        """
        kw = re.escape(keyword)
        if cls._CJK_RE.search(keyword):
            first = re.escape(keyword[0])
            last = re.escape(keyword[-1])
            return '(?<!' + first + ')' + kw + '(?!' + last + ')'
        return r'\b' + kw + r'\b'

    def parse(self, query: str) -> Dict[str, Any]:
        """解析自然语言搜索字符串，返回 FileDAO.search() 兼容的参数字典。"""
        if not query or not isinstance(query, str):
            return {}

        original = query.strip()
        query_lower = original.lower()

        result: Dict[str, Any] = {}
        matched_spans: List[Tuple[int, int]] = []  # 记录已匹配的区间，避免重复提取

        def mark_matched(match_obj):
            """记录 re 匹配的 span 并返回 span"""
            span = match_obj.span()
            matched_spans.append(span)
            return span

        # ── 1. 提取重复文件标记 ──
        dup_pattern = r'(?:重复(?:文件)?|duplicate|dup)'
        m = re.search(dup_pattern, query_lower)
        if m:
            mark_matched(m)
            result['is_duplicate'] = 1

        # ── 2. 提取文件类型 ──
        # 使用 Unicode 兼容边界（\b 对中文字符无效，参见 _kw_pattern）
        for kw, ft in self._TYPE_KEYWORDS.items():
            m = re.search(self._kw_pattern(kw), query_lower)
            if m and 'file_type' not in result:
                mark_matched(m)
                result['file_type'] = ft
                break

        # ── 3. 提取扩展名 ──
        if 'extension' not in result:
            for kw, ext in self._EXT_KEYWORDS.items():
                m = re.search(self._kw_pattern(kw), query_lower)
                if m:
                    mark_matched(m)
                    result['extension'] = ext
                    break

        # ── 4. 提取时间范围 ──
        now = datetime.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        for pattern_str, time_type in self._TIME_PATTERNS:
            m = re.search(pattern_str, query_lower)
            if not m:
                continue
            mark_matched(m)

            if time_type == 'today':
                result['start_date'] = today.strftime('%Y-%m-%d 00:00:00')
                result['end_date'] = (today + timedelta(days=1)).strftime('%Y-%m-%d 00:00:00')
            elif time_type == 'yesterday':
                d = today - timedelta(days=1)
                result['start_date'] = d.strftime('%Y-%m-%d 00:00:00')
                result['end_date'] = today.strftime('%Y-%m-%d 00:00:00')
            elif time_type == 'this_week':
                weekday = today.weekday()  # 0=Monday
                start = today - timedelta(days=weekday)
                result['start_date'] = start.strftime('%Y-%m-%d 00:00:00')
                result['end_date'] = (today + timedelta(days=1)).strftime('%Y-%m-%d 00:00:00')
            elif time_type == 'last_week':
                weekday = today.weekday()
                start = today - timedelta(days=weekday + 7)
                end = today - timedelta(days=weekday)
                result['start_date'] = start.strftime('%Y-%m-%d 00:00:00')
                result['end_date'] = end.strftime('%Y-%m-%d 00:00:00')
            elif time_type == 'this_month':
                result['start_date'] = today.replace(day=1).strftime('%Y-%m-%d 00:00:00')
                result['end_date'] = (today + timedelta(days=1)).strftime('%Y-%m-%d 00:00:00')
            elif time_type == 'last_month':
                first_this = today.replace(day=1)
                last_month_end = first_this - timedelta(days=1)
                last_month_start = last_month_end.replace(day=1)
                result['start_date'] = last_month_start.strftime('%Y-%m-%d 00:00:00')
                result['end_date'] = first_this.strftime('%Y-%m-%d 00:00:00')
            elif time_type == 'this_year':
                result['start_date'] = today.replace(month=1, day=1).strftime('%Y-%m-%d 00:00:00')
                result['end_date'] = (today + timedelta(days=1)).strftime('%Y-%m-%d 00:00:00')
            elif time_type == 'last_year':
                last_year_start = today.replace(year=today.year - 1, month=1, day=1)
                last_year_end = today.replace(month=1, day=1)
                result['start_date'] = last_year_start.strftime('%Y-%m-%d 00:00:00')
                result['end_date'] = last_year_end.strftime('%Y-%m-%d 00:00:00')
            elif time_type == 'last_n_days':
                n = int(m.group(1) or m.group(2) or 7)
                result['start_date'] = (today - timedelta(days=n)).strftime('%Y-%m-%d 00:00:00')
                result['end_date'] = (today + timedelta(days=1)).strftime('%Y-%m-%d 00:00:00')
            elif time_type == 'last_n_weeks':
                n = int(m.group(1) or m.group(2) or 1)
                result['start_date'] = (today - timedelta(weeks=n)).strftime('%Y-%m-%d 00:00:00')
                result['end_date'] = (today + timedelta(days=1)).strftime('%Y-%m-%d 00:00:00')
            elif time_type == 'last_n_months':
                n = int(m.group(1) or m.group(2) or 1)
                target_month = today.month - n
                target_year = today.year
                while target_month <= 0:
                    target_month += 12
                    target_year -= 1
                result['start_date'] = today.replace(year=target_year, month=target_month,
                                                      day=1).strftime('%Y-%m-%d 00:00:00')
                result['end_date'] = (today + timedelta(days=1)).strftime('%Y-%m-%d 00:00:00')
            elif time_type == 'specific_month':
                year, month = int(m.group(1)), int(m.group(2))
                start = datetime(year, month, 1)
                if month == 12:
                    end = datetime(year + 1, 1, 1)
                else:
                    end = datetime(year, month + 1, 1)
                result['start_date'] = start.strftime('%Y-%m-%d 00:00:00')
                result['end_date'] = end.strftime('%Y-%m-%d 00:00:00')
            elif time_type == 'this_year_month':
                month = int(m.group(1))
                start = datetime(today.year, month, 1)
                if month == 12:
                    end = datetime(today.year + 1, 1, 1)
                else:
                    end = datetime(today.year, month + 1, 1)
                result['start_date'] = start.strftime('%Y-%m-%d 00:00:00')
                result['end_date'] = end.strftime('%Y-%m-%d 00:00:00')
            elif time_type == 'en_month':
                month_map = {
                    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
                    'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12,
                }
                en_name = m.group(0).lower()
                if en_name in month_map:
                    month = month_map[en_name]
                    start = datetime(today.year, month, 1)
                    if month == 12:
                        end = datetime(today.year + 1, 1, 1)
                    else:
                        end = datetime(today.year, month + 1, 1)
                    result['start_date'] = start.strftime('%Y-%m-%d 00:00:00')
                    result['end_date'] = end.strftime('%Y-%m-%d 00:00:00')
            break  # 只取第一个时间表达式

        # ── 5. 提取大小约束 ──
        for pattern_str, op in self._SIZE_PATTERNS:
            m = re.search(pattern_str, query_lower, re.IGNORECASE)
            if not m:
                continue
            value_str = m.group(1)
            num, unit = _strip_unit(value_str)
            if num <= 0:
                continue
            bytes_val = _to_bytes(num, unit)
            mark_matched(m)

            if op == 'gt':
                result['min_size'] = bytes_val
            elif op == 'lt':
                result['max_size'] = bytes_val
            elif op in ('around', 'exact'):
                # "约 X" 或 "X" 不设约束，改为建议值；设为 name 模糊匹配
                pass
            break  # 只取第一个大小表达式

        # ── 6. 提取文件名关键词 ──
        # 排除已匹配的区间，取剩余文字作为文件名搜索词
        if 'name' not in result:
            # 构建剩余字符串
            remaining_chars = []
            spans = sorted(matched_spans)
            pos = 0
            for start, end in spans:
                if pos < start:
                    remaining_chars.append(original[pos:start])
                pos = end
            if pos < len(original):
                remaining_chars.append(original[pos:])

            remaining = ''.join(remaining_chars).strip()

            # 清理常见无意义词（中文词不用 \b，直接子串替换）
            stop_words = ['的', '文件', 'files', 'file', '个', '和', 'and', 'or', '中的',
                          'in', '有', 'with', 'containing', 'named', '名叫', '名称', '名为',
                          '是', 'is', 'are', '找', '搜索', '查', '帮我', '请', 'please',
                          '上', '里', '内', '一些', '所有', '全部',
                          '大文件', '小文件', '大', '小', '多', '少']
            for sw in stop_words:
                if sw.isascii():
                    remaining = re.sub(r'\b' + re.escape(sw) + r'\b', ' ', remaining, flags=re.IGNORECASE)
                else:
                    remaining = remaining.replace(sw, ' ')

            # 清理残留的纯数字或数字+单位片段（如 "100MB"、"500" 等已被提取为大小约束的残留）
            remaining = re.sub(r'\b\d+\s*(?:KB|MB|GB|TB|K|M|G|T)?\b', ' ', remaining, flags=re.IGNORECASE)
            # 清理残留标点
            remaining = re.sub(r'[，,。.、;；:：!！?？]+', ' ', remaining)
            remaining = re.sub(r'\s+', ' ', remaining).strip()
            if remaining:
                result['name'] = remaining

        # ── 7. 智能补充: "大文件" / "小文件" ──
        if 'min_size' not in result and 'max_size' not in result:
            m = re.search(r'(?:大文件|large\s*files?)', query_lower)
            if m:
                result['min_size'] = 100 * 1024 * 1024  # 大于 100MB
            m = re.search(r'(?:小文件|small\s*files?)', query_lower)
            if m:
                result['max_size'] = 1024 * 1024  # 小于 1MB

        return result

    def explain(self, query: str) -> str:
        """将解析结果翻译为人类可读的说明文字，用于 UI 展示。"""
        params = self.parse(query)
        if not params:
            return "未能解析任何搜索条件"

        parts = []
        type_names = {v: k for k, v in FILE_TYPE_NAMES.items()}
        type_names_rev = {v: k for k, v in type_names.items()}

        if 'name' in params:
            parts.append(f"文件名包含「{params['name']}」")
        if 'file_type' in params:
            ft = params['file_type']
            cn_name = FILE_TYPE_NAMES.get(ft, ft)
            parts.append(f"类型为「{cn_name}」")
        if 'extension' in params:
            parts.append(f"扩展名为「{params['extension']}」")
        if 'min_size' in params:
            parts.append(f"大小 ≥ {format_size(params['min_size'])}")
        if 'max_size' in params:
            parts.append(f"大小 ≤ {format_size(params['max_size'])}")
        if 'start_date' in params:
            parts.append(f"修改时间从 {params['start_date'][:10]}")
        if 'end_date' in params:
            parts.append(f"至 {params['end_date'][:10]}")
        if params.get('is_duplicate') == 1:
            parts.append("仅重复文件")

        return "，".join(parts) if parts else "未匹配到明确条件"


# ══════════════════════════════════════════════════════════════════════════════
# 2. 标签推荐器
# ══════════════════════════════════════════════════════════════════════════════

class TagRecommender:
    """基于文件属性的启发式标签推荐。

    对每个文件分析其文件名模式、路径特征、类型和大小，
    生成一组建议标签（不自动应用，仅返回列表供用户选择）。
    """

    # ── 文件名模式 → 标签 ──
    _NAME_PATTERNS: List[Tuple[str, str]] = [
        # 中文关键词
        (r'(?:^|[^a-zA-Z])报告', '报告'),
        (r'(?:^|[^a-zA-Z])合同', '合同'),
        (r'(?:^|[^a-zA-Z])发票', '发票'),
        (r'(?:^|[^a-zA-Z])简历', '简历'),
        (r'(?:^|[^a-zA-Z])笔记', '笔记'),
        (r'(?:^|[^a-zA-Z])作业', '作业'),
        (r'(?:^|[^a-zA-Z])论文', '论文'),
        (r'(?:^|[^a-zA-Z])课件', '课件'),
        (r'(?:^|[^a-zA-Z])会议', '会议'),
        (r'(?:^|[^a-zA-Z])方案', '方案'),
        (r'(?:^|[^a-zA-Z])设计', '设计'),
        (r'(?:^|[^a-zA-Z])需求', '需求'),
        (r'(?:^|[^a-zA-Z])测试', '测试'),
        (r'(?:^|[^a-zA-Z])教程', '教程'),
        (r'(?:^|[^a-zA-Z])手册', '手册'),
        (r'(?:^|[^a-zA-Z])备忘录', '备忘录'),
        (r'(?:^|[^a-zA-Z])清单', '清单'),
        (r'(?:^|[^a-zA-Z])日程', '日程'),
        (r'(?:^|[^a-zA-Z])计划', '计划'),
        (r'(?:^|[^a-zA-Z])总结', '总结'),
        (r'(?:^|[^a-zA-Z])截图', '截图'),
        (r'(?:^|[^a-zA-Z])照片', '照片'),
        (r'(?:^|[^a-zA-Z])证件照', '证件照'),
        (r'(?:^|[^a-zA-Z])壁纸', '壁纸'),
        (r'(?:^|[^a-zA-Z])模板', '模板'),
        (r'(?:^|[^a-zA-Z])草稿', '草稿'),
        (r'(?:^|[^a-zA-Z])备份', '备份'),
        (r'(?:^|[^a-zA-Z])存档', '存档'),
        (r'(?:^|[^a-zA-Z])安装', '安装包'),
        (r'(?:^|[^a-zA-Z])部署', '部署'),
        (r'(?:^|[^a-zA-Z])配置', '配置'),
        (r'(?:^|[^a-zA-Z])源码', '源码'),
        (r'(?:^|[^a-zA-Z])面试', '面试'),
        (r'(?:^|[^a-zA-Z])申请', '申请'),
        (r'(?:^|[^a-zA-Z])报销', '报销'),
        (r'(?:^|[^a-zA-Z])签证', '签证'),
        (r'(?:^|[^a-zA-Z])证明', '证明'),
        # 英文关键词
        (r'_test[_.]|_spec[_.]|test_|spec_', '测试'),
        (r'_draft[_.]|draft_', '草稿'),
        (r'_backup[_.]|backup_|_bak[_.]|_old[_.]', '备份'),
        (r'_final[_.]|_v\d+[_.]', '终稿'),
        (r'_temp[_.]|temp_|tmp[_.]|\.tmp$', '临时'),
        (r'_todo[_.]|todo_', '待办'),
        (r'_readme[_.]|readme', '说明'),
        (r'changelog|CHANGELOG', '变更日志'),
        (r'screenshot|截屏', '截图'),
        (r'invoice|receipt', '发票'),
        (r'resume|cv[_.]', '简历'),
        (r'contract|agreement', '合同'),
        (r'presentation|slides', '演示'),
        (r'proposal', '提案'),
        (r'manual|guide|tutorial', '教程'),
        (r'cheatsheet|cheat_sheet', '速查表'),
        (r'config|\.ini$|\.cfg$|\.toml$|\.env', '配置'),
        (r'dockerfile|docker-compose', 'Docker'),
        (r'makefile|\.mk$', '构建'),
        (r'\.gitignore|\.gitattributes', 'Git'),
        (r'license|LICENSE', '许可证'),
    ]

    # ── 路径模式 → 标签 ──
    _PATH_PATTERNS: List[Tuple[str, str]] = [
        (r'\\Desktop\\|\\桌面\\', '桌面文件'),
        (r'\\Downloads\\|\\下载\\', '下载文件'),
        (r'\\Documents\\|\\文档\\', '文档目录'),
        (r'\\Pictures\\|\\图片\\', '图片目录'),
        (r'\\Videos\\|\\视频\\', '视频目录'),
        (r'\\Music\\|\\音乐\\', '音乐目录'),
        (r'\\OneDrive\\', 'OneDrive'),
        (r'\\AppData\\', '应用数据'),
        (r'\\node_modules\\', 'Node模块'),
        (r'\\.git\\', 'Git仓库'),
        (r'\\.vscode\\', 'VSCode'),
        (r'\\venv\\|\\.venv\\|\\env\\', '虚拟环境'),
        (r'\\dist\\|\\build\\', '构建产物'),
        (r'\\backup\\|\\备份\\', '备份目录'),
        (r'\\temp\\|\\tmp\\|\\Temp\\|\\Tmp\\', '临时目录'),
        (r'\\projects?\\|\\项目\\', '项目目录'),
        (r'\\tests?\\|\\测试\\', '测试目录'),
    ]

    # ── 扩展名 → 标签 ──
    _EXTENSION_TAGS: Dict[str, str] = {
        '.py': 'Python', '.js': 'JavaScript', '.ts': 'TypeScript',
        '.java': 'Java', '.cpp': 'C++', '.c': 'C',
        '.go': 'Go', '.rs': 'Rust', '.swift': 'Swift',
        '.html': 'HTML', '.css': 'CSS', '.scss': 'SCSS',
        '.vue': 'Vue', '.jsx': 'React', '.tsx': 'React',
        '.json': 'JSON', '.yaml': 'YAML', '.yml': 'YAML',
        '.xml': 'XML', '.sql': 'SQL', '.md': 'Markdown',
        '.pdf': 'PDF', '.docx': 'Word', '.xlsx': 'Excel',
        '.pptx': 'PPT', '.csv': 'CSV',
        '.zip': 'ZIP', '.rar': 'RAR', '.7z': '7Z',
        '.mp3': 'MP3', '.flac': 'FLAC', '.wav': 'WAV',
        '.mp4': 'MP4', '.avi': 'AVI', '.mkv': 'MKV',
        '.psd': 'PSD', '.ai': 'AI', '.eps': 'EPS',
        '.ttf': '字体', '.otf': '字体', '.woff': '字体',
    }

    @classmethod
    def recommend(cls, file_record: dict, max_tags: int = 10) -> List[Tuple[str, float]]:
        """为单个文件推荐标签。

        Args:
            file_record: 数据库文件记录 (含 file_name, file_path, file_extension,
                         file_type, file_size, modify_time 等)
            max_tags: 最多返回的标签数

        Returns:
            [(tag_name, confidence), ...]  按置信度降序排列
        """
        suggestions: Dict[str, float] = {}

        file_name = file_record.get('file_name', '')
        file_path = file_record.get('file_path', '')
        file_ext = file_record.get('file_extension', '')
        file_type = file_record.get('file_type', '')
        file_size = file_record.get('file_size', 0)

        name_lower = file_name.lower()
        path_lower = file_path.lower()

        # ── 1. 文件名模式匹配 ──
        for pattern, tag in cls._NAME_PATTERNS:
            if re.search(pattern, name_lower):
                suggestions[tag] = max(suggestions.get(tag, 0), 0.8)

        # ── 2. 路径特征 ──
        for pattern, tag in cls._PATH_PATTERNS:
            if re.search(pattern, path_lower):
                suggestions[tag] = max(suggestions.get(tag, 0), 0.85)

        # ── 3. 扩展名标签 ──
        ext_lower = file_ext.lower() if file_ext else ''
        if ext_lower in cls._EXTENSION_TAGS:
            tag = cls._EXTENSION_TAGS[ext_lower]
            suggestions[tag] = max(suggestions.get(tag, 0), 0.7)

        # ── 4. 文件类型标签 ──
        if file_type and file_type in FILE_TYPE_NAMES and file_type != 'other':
            cn_type = FILE_TYPE_NAMES[file_type]
            suggestions[cn_type] = max(suggestions.get(cn_type, 0), 0.5)

        # ── 5. 大小特征 ──
        if file_size and file_size > 0:
            if file_size >= 1024 * 1024 * 1024:  # >= 1GB
                suggestions['大型文件'] = 0.7
            elif file_size >= 100 * 1024 * 1024:  # >= 100MB
                suggestions['大文件'] = 0.5
            elif file_size <= 1024:  # <= 1KB
                suggestions['微型文件'] = 0.6
            elif file_size <= 100 * 1024:  # <= 100KB
                suggestions['小文件'] = 0.4

        # ── 6. 时间特征 ──
        mtime = file_record.get('modify_time')
        if mtime:
            if isinstance(mtime, str):
                try:
                    mtime = datetime.strptime(mtime[:10], '%Y-%m-%d')
                except ValueError:
                    mtime = None
            if isinstance(mtime, datetime):
                days_ago = (datetime.now() - mtime).days
                if days_ago > 365:
                    suggestions['历史文件'] = 0.6
                elif days_ago > 90:
                    suggestions['旧文件'] = 0.4
                elif days_ago <= 7:
                    suggestions['近期文件'] = 0.5
                elif days_ago <= 1:
                    suggestions['今日文件'] = 0.7

        # ── 排序并返回 Top-N ──
        sorted_tags = sorted(suggestions.items(), key=lambda x: x[1], reverse=True)
        return sorted_tags[:max_tags]

    @classmethod
    def recommend_batch(cls, file_records: list, max_tags: int = 10) -> Dict[int, List[Tuple[str, float]]]:
        """批量推荐标签。

        Returns:
            {file_id: [(tag_name, confidence), ...]}
        """
        result: Dict[int, List[Tuple[str, float]]] = {}
        for record in file_records:
            fid = record.get('id')
            if fid is not None:
                result[fid] = cls.recommend(record, max_tags)
        return result


# ══════════════════════════════════════════════════════════════════════════════
# 3. 清理建议引擎
# ══════════════════════════════════════════════════════════════════════════════

class CleanupAdvisor:
    """文件清理建议引擎。

    分析数据库中的文件记录，识别以下清理候选：
      1. 重复文件 —— 浪费磁盘空间
      2. 长期未修改文件 —— 可能已废弃
      3. 临时文件 —— .tmp / ~$ / .cache 等
      4. 空文件 —— 大小为 0 的文件
      5. 超大文件 —— 占用大量空间
      6. 孤立文件 —— 无标签、无分类的文件（可能不重要）
    """

    # 临时文件模式
    _TEMP_PATTERNS = [
        r'\.tmp$', r'\.temp$', r'~\$', r'\.cache$', r'\.log\.\d+$',
        r'\.bak$', r'\.swp$', r'\.swo$', r'\.orig$', r'\.old$',
        r'\.DS_Store$', r'Thumbs\.db$', r'desktop\.ini$',
        r'\.crdownload$', r'\.part$', r'\.partial$',
        r'_placeholder', r'\.lock$',
    ]

    def __init__(self, file_dao, tag_dao, cls_dao):
        """初始化清理建议引擎。

        Args:
            file_dao: FileDAO 实例
            tag_dao: TagDAO 实例
            cls_dao: ClassificationDAO 实例
        """
        self.file_dao = file_dao
        self.tag_dao = tag_dao
        self.cls_dao = cls_dao

    def analyze(self) -> Dict[str, Any]:
        """执行全面分析，返回清理建议汇总。"""
        summary = {
            'total_active_files': self.file_dao.count_active(),
            'total_size': self.file_dao.get_total_size(),
            'categories': [],
        }

        # ── 1. 重复文件分析 ──
        dup_result = self._analyze_duplicates()
        if dup_result:
            summary['categories'].append(dup_result)

        # ── 2. 长期未修改文件 ──
        old_result = self._analyze_old_files()
        if old_result:
            summary['categories'].append(old_result)

        # ── 3. 临时文件 ──
        temp_result = self._analyze_temp_files()
        if temp_result:
            summary['categories'].append(temp_result)

        # ── 4. 空文件 ──
        empty_result = self._analyze_empty_files()
        if empty_result:
            summary['categories'].append(empty_result)

        # ── 5. 超大文件 ──
        large_result = self._analyze_large_files()
        if large_result:
            summary['categories'].append(large_result)

        # ── 6. 孤立文件 ──
        orphan_result = self._analyze_orphan_files()
        if orphan_result:
            summary['categories'].append(orphan_result)

        # 计算总可释放空间
        total_savings = sum(c.get('potential_savings', 0) for c in summary['categories'])
        summary['total_potential_savings'] = total_savings

        return summary

    def _analyze_duplicates(self) -> Optional[Dict[str, Any]]:
        """分析重复文件"""
        try:
            dup_groups = self.file_dao.get_duplicate_groups_paginated(page=0, page_size=1000)
            if not dup_groups:
                return None

            total_wasted = self.file_dao.get_duplicate_total_wasted()
            dup_file_count = sum(g['file_count'] for g in dup_groups)

            return {
                'category': '重复文件',
                'icon': 'copy',
                'count': dup_file_count,
                'group_count': len(dup_groups),
                'potential_savings': total_wasted,
                'severity': 'high' if total_wasted > 100 * 1024 * 1024 else 'medium',
                'description': f"发现 {len(dup_groups)} 组重复文件，共 {dup_file_count} 个文件，"
                               f"可释放 {format_size(total_wasted)} 空间",
                'action': '去重处理',
            }
        except Exception as e:
            logger.warning(f"分析重复文件失败: {e}")
            return None

    def _analyze_old_files(self) -> Optional[Dict[str, Any]]:
        """分析长期未修改的文件（超过 1 年未修改）"""
        try:
            one_year_ago = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
            old_files = self.file_dao.search(
                start_date='2000-01-01',
                end_date=one_year_ago + ' 23:59:59',
            )
            if not old_files:
                return None

            total_size = sum(f.get('file_size', 0) for f in old_files)

            return {
                'category': '长期未修改文件',
                'icon': 'clock',
                'count': len(old_files),
                'potential_savings': total_size,
                'severity': 'medium',
                'description': f"发现 {len(old_files)} 个超过 1 年未修改的文件，"
                               f"占用 {format_size(total_size)}",
                'action': '归档或删除',
                'samples': old_files[:5],  # 取前 5 个作为样本
            }
        except Exception as e:
            logger.warning(f"分析旧文件失败: {e}")
            return None

    def _analyze_temp_files(self) -> Optional[Dict[str, Any]]:
        """分析临时文件和缓存文件"""
        try:
            all_files = self.file_dao.get_all_active()
            temp_files = []
            for f in all_files:
                name = f.get('file_name', '')
                for pattern in self._TEMP_PATTERNS:
                    if re.search(pattern, name):
                        temp_files.append(f)
                        break

            if not temp_files:
                return None

            total_size = sum(f.get('file_size', 0) for f in temp_files)

            return {
                'category': '临时/缓存文件',
                'icon': 'trash',
                'count': len(temp_files),
                'potential_savings': total_size,
                'severity': 'low',
                'description': f"发现 {len(temp_files)} 个临时/缓存文件，"
                               f"占用 {format_size(total_size)}",
                'action': '安全清理',
                'samples': temp_files[:5],
            }
        except Exception as e:
            logger.warning(f"分析临时文件失败: {e}")
            return None

    def _analyze_empty_files(self) -> Optional[Dict[str, Any]]:
        """分析空文件"""
        try:
            empty_files = self.file_dao.search(max_size=0)
            if not empty_files:
                return None

            return {
                'category': '空文件',
                'icon': 'file',
                'count': len(empty_files),
                'potential_savings': 0,
                'severity': 'low',
                'description': f"发现 {len(empty_files)} 个空文件（大小为 0 字节）",
                'action': '检查后删除',
                'samples': empty_files[:5],
            }
        except Exception as e:
            logger.warning(f"分析空文件失败: {e}")
            return None

    def _analyze_large_files(self) -> Optional[Dict[str, Any]]:
        """分析超大文件（> 500MB）"""
        try:
            large_files = self.file_dao.search(min_size=500 * 1024 * 1024)
            if not large_files:
                return None

            total_size = sum(f.get('file_size', 0) for f in large_files)
            # 取 Top 10
            sorted_files = sorted(large_files, key=lambda x: x.get('file_size', 0), reverse=True)

            return {
                'category': '超大文件',
                'icon': 'hdd',
                'count': len(large_files),
                'potential_savings': total_size,
                'severity': 'medium' if total_size < 10 * 1024 * 1024 * 1024 else 'high',
                'description': f"发现 {len(large_files)} 个超过 500MB 的大文件，"
                               f"合计 {format_size(total_size)}",
                'action': '检查是否需要保留',
                'samples': sorted_files[:5],
            }
        except Exception as e:
            logger.warning(f"分析大文件失败: {e}")
            return None

    def _analyze_orphan_files(self) -> Optional[Dict[str, Any]]:
        """分析无标签、无分类的孤立文件"""
        try:
            # 取一部分活跃文件做分析（避免全量扫描）
            recent_files = self.file_dao.search_paginated(page=0, page_size=500)
            if not recent_files:
                return None

            file_ids = [f['id'] for f in recent_files]
            file_id_set = set(file_ids)

            # 查有标签的文件
            tags_by_file = self.tag_dao.get_all_tags_by_file(file_ids)
            tagged_ids = set(tags_by_file.keys())

            # 查有分类的文件
            cls_by_file = self.cls_dao.get_by_file_ids(file_ids)
            classified_ids = set(cls_by_file.keys())

            # 无标签且无分类的 = 孤立文件
            orphan_ids = file_id_set - tagged_ids - classified_ids
            if not orphan_ids:
                return None

            orphan_files = [f for f in recent_files if f['id'] in orphan_ids]
            total_size = sum(f.get('file_size', 0) for f in orphan_files)

            return {
                'category': '未归类的文件',
                'icon': 'folder',
                'count': len(orphan_files),
                'potential_savings': total_size,
                'severity': 'info',
                'description': f"最近扫描的 500 个文件中有 {len(orphan_files)} 个"
                               f"既无标签也无分类，帮助整理？",
                'action': '运行分类和标签推荐',
                'samples': orphan_files[:5],
            }
        except Exception as e:
            logger.warning(f"分析孤立文件失败: {e}")
            return None


# ══════════════════════════════════════════════════════════════════════════════
# 顶层外观
# ══════════════════════════════════════════════════════════════════════════════

class RuleEngine:
    """规则引擎统一入口。

    整合三大功能模块：
      - NL 搜索解析
      - 标签推荐
      - 清理建议

    用法示例:
        engine = RuleEngine(file_dao, tag_dao, cls_dao)
        params = engine.parse_search("大于100MB的图片")        # NL -> 结构化搜索参数
        tags = engine.recommend_tags(file_record)              # 文件 -> 推荐标签
        report = engine.cleanup_report()                       # 数据库 -> 清理报告
    """

    def __init__(self, file_dao=None, tag_dao=None, cls_dao=None):
        self.search_parser = NLSearchParser()
        self.tag_recommender = TagRecommender()
        self.cleanup_advisor = CleanupAdvisor(file_dao, tag_dao, cls_dao) if file_dao else None

    def parse_search(self, query: str) -> Dict[str, Any]:
        """解析自然语言搜索查询"""
        return self.search_parser.parse(query)

    def explain_search(self, query: str) -> str:
        """解释解析结果"""
        return self.search_parser.explain(query)

    def recommend_tags(self, file_record: dict, max_tags: int = 10) -> List[Tuple[str, float]]:
        """为单个文件推荐标签"""
        return self.tag_recommender.recommend(file_record, max_tags)

    def recommend_tags_batch(self, file_records: list,
                              max_tags: int = 10) -> Dict[int, List[Tuple[str, float]]]:
        """批量推荐标签"""
        return self.tag_recommender.recommend_batch(file_records, max_tags)

    def cleanup_report(self) -> Optional[Dict[str, Any]]:
        """生成清理建议报告"""
        if not self.cleanup_advisor:
            return None
        return self.cleanup_advisor.analyze()
