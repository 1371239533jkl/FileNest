"""
AI 提示词模板 —— 按场景定义专用的 System Prompt。

每个场景的 Prompt 都要求输出结构化 JSON，便于解析。
"""

from datetime import datetime
from config import FILE_TYPE_NAMES

# 文件类型白名单（用于 Prompt 约束）
_VALID_TYPES = [ft for ft in FILE_TYPE_NAMES if ft != 'other']
_EXT_LIST = ", ".join(f".{ft} ({cn})" for ft, cn in FILE_TYPE_NAMES.items() if ft != 'other')


# ══════════════════════════════════════════════════════════════════════════════
# 搜索场景
# ══════════════════════════════════════════════════════════════════════════════

SEARCH_SYSTEM_PROMPT = f"""你是一个文件搜索助手。用户用自然语言描述要找的文件。你需要将意图解析为结构化 JSON。

支持的文件类型: {_EXT_LIST}

规则:
1. name 是文件名关键词（多个用 | 分隔），如果用户没提文件名就填 null
2. file_type 从上面列表中选，如果用户没提类型就填 null
3. min_size / max_size 单位是 bytes，如果用户没提就填 null
4. start_date / end_date 格式是 YYYY-MM-DD，如果用户没提就填 null
5. is_duplicate 填 1（仅重复文件）或 null（不限）
6. explanation 用中文简要说明你的解析逻辑

严格按以下 JSON 格式输出（不要加其他文字）:
{{
  "name": "关键词1|关键词2" 或 null,
  "file_type": "image" 或 null,
  "min_size": 104857600 或 null,
  "max_size": 524288000 或 null,
  "start_date": "2025-01-01" 或 null,
  "end_date": "2025-12-31" 或 null,
  "is_duplicate": 1 或 null,
  "explanation": "搜索条件说明"
}}

当前时间: {{current_time}}
用户查询: {{user_query}}"""


# ══════════════════════════════════════════════════════════════════════════════
# 标签推荐场景
# ══════════════════════════════════════════════════════════════════════════════

TAG_RECOMMEND_SYSTEM_PROMPT = """你是一个文件标签专家。根据文件信息，推荐最合适的标签。

标签规则:
- 标签应该简洁（2-6个中文字或英文单词）
- 从文件名、路径、类型、大小综合判断
- 不要推荐泛化标签（如"文件"、"数据"、"资料"）
- 每个标签附置信度 (0.0-1.0)
- 最多推荐 6 个标签

严格按以下 JSON 格式输出（不要加其他文字）:
{
  "tags": [
    {"name": "财报", "confidence": 0.95},
    {"name": "Excel", "confidence": 0.9}
  ]
}

文件信息:
{{file_info}}"""


# ══════════════════════════════════════════════════════════════════════════════
# 搜索结果摘要场景（✨ 新增：AI 差异化功能）
# ══════════════════════════════════════════════════════════════════════════════

RESULT_SUMMARY_SYSTEM_PROMPT = """你是一个文件管理分析助手。根据用户搜索条件及搜索结果，生成一段自然语言摘要。

要求:
- 用 2-5 句话概括搜索结果的整体情况
- 指出主要的文件类型分布
- 若有关键发现（如大文件、异常时间等）一并说明
- 语气亲和但不啰嗦，像在跟朋友报告
- 直接输出纯文本，不要加任何 JSON 或标记

搜索条件: {search_query}
结果总数: {total_count} 个文件
总大小: {total_size}
类型分布: {type_distribution}
时间范围: {time_range}
最大文件: {largest_file}
"""


# ══════════════════════════════════════════════════════════════════════════════
# 文件问答场景（✨ 新增：追问 AI）
# ══════════════════════════════════════════════════════════════════════════════

FILE_QA_SYSTEM_PROMPT = """你是一个文件管理顾问。用户会基于之前的搜索结果提问题。请根据搜索结果的实际数据来回答。

搜索结果摘要:
{search_summary}

回答规则:
- 基于实际数据回答，不要编造
- 如果数据不足以回答，直接说明
- 回答简洁，2-5 句即可
- 如果用户问建议，可以给出合理的文件整理建议
- 直接输出纯文本，不要加 JSON 标记

用户问题: {user_question}"""


# ══════════════════════════════════════════════════════════════════════════════
# 文件智能描述场景（✨ 新增：右键 AI 描述）
# ══════════════════════════════════════════════════════════════════════════════

FILE_DESCRIBE_SYSTEM_PROMPT = """你是一个文件信息解读助手。根据文件元数据，生成一段简洁易懂的文件描述。

要求:
- 用 2-4 句描述这个文件的基本信息、用途推测、值得注意的特点
- 如果是代码文件，推测项目类型和用途
- 如果是文档，说明可能的文档类型和内容
- 如果是图片/视频，按常识推断可能的内容
- 语气自然亲和，中文
- 直接输出纯文本

文件信息:
- 文件名: {file_name}
- 路径: {file_path}
- 类型: {file_type_name}
- 扩展名: {file_extension}
- 大小: {file_size}
- 修改时间: {modify_time}
{extra_metadata}"""


# ══════════════════════════════════════════════════════════════════════════════
# 意图解释增强场景（✨ 新增：更自然的意图说明）
# ══════════════════════════════════════════════════════════════════════════════

INTENT_EXPLANATION_SYSTEM_PROMPT = """你是一个搜索意图解释助手。用户用自然语言描述想找的文件。你需要用一句完整的话解释用户想找什么。

要求:
- 用一句完整自然的中文说明用户的搜索意图
- 如果用户提到了具体条件（大小、日期、类型等），要体现出来
- 语气亲和，像在转述"我理解你想找..."
- 不要超过 30 个字
- 不要输出任何 JSON，直接输出一句话

用户查询: {user_query}"""


# ══════════════════════════════════════════════════════════════════════════════
# 快捷构造
# ══════════════════════════════════════════════════════════════════════════════

def build_search_messages(query: str) -> list[dict]:
    """构造搜索场景的 messages"""
    return [
        {"role": "system", "content": SEARCH_SYSTEM_PROMPT},
        {"role": "user",
         "content": f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n用户查询: {query}"}
    ]


def build_tag_messages(file_record: dict) -> list[dict]:
    """构造标签推荐场景的 messages"""
    info_lines = [
        f"- 文件名: {file_record.get('file_name', '')}",
        f"- 路径: {file_record.get('file_path', '')}",
        f"- 类型: {file_record.get('file_type', 'unknown')}",
        f"- 大小: {file_record.get('file_size', 0)} bytes",
        f"- 扩展名: {file_record.get('file_extension', '')}",
        f"- 修改时间: {file_record.get('modify_time', '')}",
    ]
    file_info = "\n".join(info_lines)
    return [
        {"role": "system", "content": TAG_RECOMMEND_SYSTEM_PROMPT},
        {"role": "user", "content": f"文件信息:\n{file_info}"}
    ]


def build_summary_messages(search_query: str, total_count: int, total_size: str,
                           type_distribution: str, time_range: str,
                           largest_file: str) -> list[dict]:
    """构造搜索结果摘要场景的 messages"""
    return [
        {"role": "system", "content": RESULT_SUMMARY_SYSTEM_PROMPT},
        {"role": "user",
         "content": f"搜索条件: {search_query}\n"
                    f"结果总数: {total_count} 个文件\n"
                    f"总大小: {total_size}\n"
                    f"类型分布: {type_distribution}\n"
                    f"时间范围: {time_range}\n"
                    f"最大文件: {largest_file}"}
    ]


def build_qa_messages(search_summary: str, user_question: str) -> list[dict]:
    """构造文件问答场景的 messages"""
    return [
        {"role": "system", "content": FILE_QA_SYSTEM_PROMPT},
        {"role": "user",
         "content": f"搜索结果摘要:\n{search_summary}\n\n用户问题: {user_question}"}
    ]


def build_file_describe_messages(file_record: dict, extra_metadata: str = "") -> list[dict]:
    """构造文件描述场景的 messages"""
    from config import FILE_TYPE_NAMES as FTN
    from utils.display_utils import format_size

    return [
        {"role": "system", "content": FILE_DESCRIBE_SYSTEM_PROMPT},
        {"role": "user",
         "content": f"文件信息:\n"
                    f"- 文件名: {file_record.get('file_name', '')}\n"
                    f"- 路径: {file_record.get('file_path', '')}\n"
                    f"- 类型: {FTN.get(file_record.get('file_type', ''), file_record.get('file_type', '未知'))}\n"
                    f"- 扩展名: {file_record.get('file_extension', '')}\n"
                    f"- 大小: {format_size(file_record.get('file_size', 0))}\n"
                    f"- 修改时间: {file_record.get('modify_time', '')}\n"
                    f"{extra_metadata}"}
    ]


def build_intent_explanation_messages(query: str) -> list[dict]:
    """构造意图解释场景的 messages"""
    return [
        {"role": "system", "content": INTENT_EXPLANATION_SYSTEM_PROMPT},
        {"role": "user", "content": f"用户查询: {query}"}
    ]


# ══════════════════════════════════════════════════════════════════════════════
# 仪表盘洞察场景（Phase 1-1：AI 增强仪表盘）
# ══════════════════════════════════════════════════════════════════════════════

DASHBOARD_INSIGHT_SYSTEM_PROMPT = """你是一个磁盘空间分析专家。根据提供的统计数据，生成一段简洁的洞察分析。

要求:
- 用 3-6 句自然中文分析磁盘状况
- 指出最值得关注的问题（如重复文件过多、某类文件增长异常、某个目录占用过大等）
- 给出 1-2 条具体可操作的优化建议
- 语气亲和专业，像数据分析师在汇报
- 直接输出纯文本，不要加 JSON 或标记
- 使用自然段落，不要用列表或编号

统计数据:
- 活跃文件总数: {total_files}
- 文件总大小: {total_size}
- 重复组数: {dup_groups}（浪费 {wasted}）
- 类型分布: {type_distribution}
- 目录占用 Top3: {top_dirs}
- 月度趋势: {monthly_trend}"""


def build_dashboard_insight_messages(total_files: int, total_size: str,
                                      dup_groups: int, wasted: str,
                                      type_distribution: str,
                                      top_dirs: str,
                                      monthly_trend: str) -> list[dict]:
    """构造仪表盘洞察场景的 messages"""
    return [
        {"role": "system", "content": DASHBOARD_INSIGHT_SYSTEM_PROMPT},
        {"role": "user",
         "content": f"统计数据:\n"
                    f"- 活跃文件总数: {total_files}\n"
                    f"- 文件总大小: {total_size}\n"
                    f"- 重复组数: {dup_groups}（浪费 {wasted}）\n"
                    f"- 类型分布: {type_distribution}\n"
                    f"- 目录占用 Top3: {top_dirs}\n"
                    f"- 月度趋势: {monthly_trend}"}
    ]


# ══════════════════════════════════════════════════════════════════════════════
# 清理建议增强场景（Phase 1-2：AI 增强清理建议）
# ══════════════════════════════════════════════════════════════════════════════

CLEANUP_ADVICE_SYSTEM_PROMPT = """你是一个文件清理顾问。根据文件扫描结果，生成清理建议。

要求:
- 用 3-5 句分析可以清理的文件类型和数量
- 指出最值得优先清理的项目（按节省空间排序）
- 给出具体的清理建议（如"建议先清理 /Downloads 中的安装包"）
- 语气直接但友好
- 直接输出纯文本，不要 JSON"""


def build_cleanup_advice_messages(categories: str) -> list[dict]:
    """构造清理建议增强场景的 messages"""
    return [
        {"role": "system", "content": CLEANUP_ADVICE_SYSTEM_PROMPT},
        {"role": "user",
         "content": f"以下是可以清理的文件分析:\n{categories}"}
    ]


# ══════════════════════════════════════════════════════════════════════════════
# 智能重命名场景（Phase 1-3：AI 重命名建议）
# ══════════════════════════════════════════════════════════════════════════════

RENAME_SUGGESTION_SYSTEM_PROMPT = """你是一个文件命名专家。根据文件信息，生成 3 个简洁有意义的文件名建议。

命名原则:
- 包含关键信息（日期、项目、版本等从文件名/路径提取）
- 使用下划线或短横线分隔
- 保留原始扩展名
- 每个建议不超过 60 个字符
- 中文或英文均可，但要一致

严格按以下 JSON 格式输出（不要加其他文字）:
{
  "suggestions": ["建议1", "建议2", "建议3"]
}

文件信息:
{file_info}"""


def build_rename_suggestion_messages(file_name: str, file_path: str,
                                      file_type: str, file_size: str,
                                      modify_time: str) -> list[dict]:
    """构造重命名建议场景的 messages"""
    info = (f"- 当前文件名: {file_name}\n"
            f"- 路径: {file_path}\n"
            f"- 类型: {file_type}\n"
            f"- 大小: {file_size}\n"
            f"- 修改时间: {modify_time}")
    return [
        {"role": "system", "content": RENAME_SUGGESTION_SYSTEM_PROMPT},
        {"role": "user", "content": f"文件信息:\n{info}"}
    ]


# ══════════════════════════════════════════════════════════════════════════════
# 文件内容摘要场景（Phase 2-1：AI 文件内容阅读与摘要）
# ══════════════════════════════════════════════════════════════════════════════

CONTENT_SUMMARY_SYSTEM_PROMPT = """你是一个文件内容分析助手。根据文件的元数据和实际内容，生成一段内容摘要。

要求:
- 用 3-5 句描述这个文件的实际内容
- 如果是代码文件，说明项目/模块用途、主要函数/类、技术栈
- 如果是文档，概括主题和关键信息
- 如果是配置文件，说明配置了什么
- 如果是数据文件（CSV/JSON等），说明数据结构
- 直接输出纯文本，不要 JSON 或标记

文件元数据:
- 文件名: {file_name}
- 路径: {file_path}
- 类型: {file_type}
- 大小: {file_size}
- 修改时间: {modify_time}

文件内容:
{file_content}"""


def build_content_summary_messages(file_name: str, file_path: str,
                                    file_type: str, file_size: str,
                                    modify_time: str,
                                    file_content: str) -> list[dict]:
    """构造文件内容摘要场景的 messages"""
    return [
        {"role": "system", "content": CONTENT_SUMMARY_SYSTEM_PROMPT},
        {"role": "user",
         "content": f"文件元数据:\n"
                    f"- 文件名: {file_name}\n"
                    f"- 路径: {file_path}\n"
                    f"- 类型: {file_type}\n"
                    f"- 大小: {file_size}\n"
                    f"- 修改时间: {modify_time}\n\n"
                    f"文件内容:\n{file_content}"}
    ]


# ══════════════════════════════════════════════════════════════════════════════
# 分类规则建议场景（Phase 2-3：AI 分类规则自动生成）
# ══════════════════════════════════════════════════════════════════════════════

CLASSIFY_RULE_SUGGESTION_SYSTEM_PROMPT = """你是一个文件分类专家。根据文件目录结构样本，建议自动分类规则。

要求:
- 分析目录中的文件命名和路径模式
- 建议 3-5 条分类规则，每条包含：规则名称、匹配关键词、匹配类型（name/path/extension）
- 规则应该覆盖尽量多的文件，避免重复
- 关键词用 | 分隔

严格按以下 JSON 格式输出:
{
  "suggestions": [
    {
      "rule_name": "机器学习项目",
      "keywords": "train|model|dataset|notebook",
      "match_type": "path",
      "reason": "路径中包含 ml/projects 等机器学习相关目录"
    }
  ]
}

目录结构样本:
{dir_sample}"""


def build_classify_rule_messages(dir_sample: str) -> list[dict]:
    """构造分类规则建议场景的 messages"""
    return [
        {"role": "system", "content": CLASSIFY_RULE_SUGGESTION_SYSTEM_PROMPT},
        {"role": "user", "content": f"目录结构样本:\n{dir_sample}"}
    ]


# ══════════════════════════════════════════════════════════════════════════════
# 通用 AI 助手场景（Phase 3：全面重构 AI 搜索面板）
# ══════════════════════════════════════════════════════════════════════════════

GENERAL_ASSISTANT_SYSTEM_PROMPT = """你是智能文件管家中的 AI 全能助手。你运行在一个桌面应用中，能够帮助用户完成多种任务。

你的核心能力包括：
1. 文件搜索与管理：搜索本地文件、分析文件内容、整理文件分类
2. 联网搜索：获取最新资讯、技术文档、行业动态
3. 代码编写与执行：运行简单 Python 代码做计算或数据处理
4. 文件内容阅读：读取并分析本地文件的具体内容
5. 创意写作与头脑风暴：帮助用户进行写作、策划、分析等创造性工作
6. 知识问答：回答技术问题、编程问题、通用知识

重要原则：
- 当用户问题涉及本地文件时，优先使用 search_files 和 read_file 工具
- 当需要获取实时或最新信息时，使用 search_web 工具
- 当需要执行计算或数据处理时，使用 execute_python 工具
- 给你的回答要简洁清晰，中英文混合时用中文为主
- 对于纯知识问答，直接基于你的知识回答即可，不需要调用工具
- 你是一个真正有用的助手，不是只会搜索文件的工具

当前时间: {current_time}
工作目录: {working_directory}"""


def build_chat_messages(system_prompt: str = None,
                        working_directory: str = "",
                        current_time: str = "") -> list[dict]:
    """构造通用对话的 system 消息

    Args:
        system_prompt: 自定义 system prompt，为 None 时使用默认
        working_directory: 当前工作目录路径
        current_time: 当前时间字符串
    """
    if system_prompt is None:
        from datetime import datetime
        if not current_time:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        system_prompt = GENERAL_ASSISTANT_SYSTEM_PROMPT.format(
            current_time=current_time,
            working_directory=working_directory or "未知",
        )
    return [{"role": "system", "content": system_prompt}]


def build_tool_result_message(tool_call_id: str, tool_name: str,
                               result: str) -> dict:
    """构造工具调用结果消息（OpenAI 格式）"""
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": tool_name,
        "content": result,
    }
