"""
AI 主入口层 —— 统一封装 LLM 调用 + 降级策略 + 多后端支持。

用法:
    layer = AILayer()
    result = layer.search("大于100MB的图片")  # dict 或 None
    summary = layer.summarize_results(query, files)  # 自然语言摘要
    answer = layer.answer_question(context_summary, question)  # 追问
    desc = layer.describe_file(file_record)  # 文件智能描述
    reply = layer.chat(messages, tools=tools)  # 通用对话（含工具调用）
    reply = layer.chat_with_tools(conversation, registry)  # 多轮工具调用
"""

from typing import Optional, List, Tuple, Generator

from core.ai_backends import OpenAICompatibleBackend, AIResult, AIStreamChunk
from core.ai_model_config import AIModelConfigManager
from core.ai_prompts import (
    build_search_messages, build_tag_messages,
    build_summary_messages, build_qa_messages,
    build_file_describe_messages, build_intent_explanation_messages,
    build_dashboard_insight_messages, build_cleanup_advice_messages,
    build_rename_suggestion_messages, build_content_summary_messages,
    build_classify_rule_messages,
    build_chat_messages,
)
from core.ai_response import ResponseParser
from core.ai_preprocessor import Preprocessor, OutputValidator
from core.rule_engine import NLSearchParser, TagRecommender
from config import AI_CONFIG, FILE_TYPE_NAMES
from utils.display_utils import format_size
from utils.logger import logger


class AILayer:
    """AI 功能统一入口，支持多后端 + 规则引擎降级

    优先级: 自定义模型配置 > config.py 默认配置 > 规则引擎降级
    """

    def __init__(self):
        self._model_cfg = AIModelConfigManager()
        self._backend: Optional[OpenAICompatibleBackend] = None
        self.search_parser = NLSearchParser()
        self.tag_recommender = TagRecommender()
        self._init_backend()

    def _init_backend(self):
        """初始化 AI 后端：优先使用用户自定义模型配置，否则回退 config.py"""
        active = self._model_cfg.get_active()
        if active and active.api_key:
            try:
                self._backend = OpenAICompatibleBackend(
                    api_key=active.api_key,
                    base_url=active.base_url,
                    model=active.model,
                    timeout=active.timeout,
                )
                logger.info(f"AI 已启用 (自定义): {active.name} / {active.model}")
                return
            except Exception as e:
                logger.error(f"自定义 AI 后端初始化失败: {e}")

        # 回退 config.py 默认配置
        if AI_CONFIG.get('enabled') and AI_CONFIG.get('api_key'):
            try:
                self._backend = OpenAICompatibleBackend(
                    api_key=AI_CONFIG['api_key'],
                    base_url=AI_CONFIG.get('base_url', 'https://api.deepseek.com/v1'),
                    model=AI_CONFIG.get('model', 'deepseek-v4-flash'),
                    timeout=AI_CONFIG.get('timeout', 20),
                )
                logger.info(f"AI 已启用 (默认配置): {AI_CONFIG.get('model')}")
                return
            except Exception as e:
                logger.error(f"默认 AI 后端初始化失败: {e}")

        logger.warning("AI 未启用：未配置任何可用的 AI 后端")

    @property
    def enabled(self) -> bool:
        return self._backend is not None

    @property
    def backend_model_name(self) -> str:
        """当前使用的模型名称（用于 UI 展示）"""
        if self._backend:
            return self._backend.model
        active = self._model_cfg.get_active()
        if active:
            return f"{active.name} / {active.model}"
        return "未配置"

    def reload_backend(self):
        """重新加载后端配置（用户修改模型配置后调用）"""
        self._init_backend()
        # 清除工具注册表缓存
        self._tool_registry = None

    @property
    def tool_registry(self):
        """懒加载工具注册表"""
        if not hasattr(self, '_tool_registry') or self._tool_registry is None:
            from core.ai_tools import create_default_registry, ToolRegistry
            from database.db_manager import DBManager
            try:
                db = DBManager()
            except Exception:
                db = None
            self._tool_registry = create_default_registry(db_manager=db, ai_layer=self)
        return self._tool_registry

    @property
    def db_manager(self):
        """获取数据库管理器（用于工具调用）"""
        if not hasattr(self, '_db_manager') or self._db_manager is None:
            from database.db_manager import DBManager
            try:
                self._db_manager = DBManager()
            except Exception:
                self._db_manager = None
        return self._db_manager

    # ══════════════════════════════════════════════════════════════════════════
    # 智能搜索（保持原有逻辑）
    # ══════════════════════════════════════════════════════════════════════════

    def search(self, query: str) -> Tuple[Optional[dict], str]:
        """智能搜索: 优先 LLM 解析，降级规则引擎。

        Returns:
            (params_dict, source)  — source 为 "ai" | "rules"
        """
        if Preprocessor.is_simple(query):
            params = self.search_parser.parse(query)
            if params:
                logger.debug(f"简单查询走规则引擎: {query!r}")
                return params, "rules"
            return None, "none"

        if self.enabled:
            try:
                safe, reason = Preprocessor.check_safety(query)
                if not safe:
                    logger.warning(f"搜索输入不安全: {reason}")
                    params = self.search_parser.parse(query)
                    return params, "rules"

                messages = build_search_messages(query)
                result = self._backend.chat(messages, max_tokens=300, temperature=0.05)

                safe_out, reason_out = OutputValidator.check_dangerous(result.content)
                if not safe_out:
                    logger.warning(f"LLM 输出不安全: {reason_out}")
                    params = self.search_parser.parse(query)
                    return params, "rules"

                params = ResponseParser.parse_search(result.content)
                if params:
                    valid, errors = OutputValidator.validate_search_params(params)
                    if not valid:
                        logger.warning(f"LLM 搜索参数校验失败: {errors}")
                        params = self.search_parser.parse(query)
                        return params, "rules"

                    logger.info(f"AI 搜索解析成功: {params.get('_explanation', '')} ({result.latency_ms}ms)")
                    return params, "ai"
                else:
                    logger.warning("AI 搜索解析失败，降级规则引擎")

            except Exception as e:
                logger.warning(f"AI 搜索调用失败: {e}，降级规则引擎")

        logger.debug(f"降级规则引擎解析搜索: {query!r}")
        params = self.search_parser.parse(query)
        return params, "rules"

    # ══════════════════════════════════════════════════════════════════════════
    # 搜索结果摘要（✨ 新增：AI 差异化核心功能）
    # ══════════════════════════════════════════════════════════════════════════

    def summarize_results(self, search_query: str, files: list,
                          total_count: int = None) -> Optional[str]:
        """对搜索结果生成自然语言摘要。

        Args:
            search_query: 用户的搜索查询文本
            files: 搜索结果文件列表（当前页数据即可）
            total_count: 总文件数（用于统计）

        Returns:
            摘要文本，或 None（AI 不可用时）
        """
        if not self.enabled or not files:
            return None

        try:
            count = total_count or len(files)
            total_bytes = sum(f.get('file_size', 0) for f in files[:50])

            # 类型分布
            type_counts = {}
            for f in files[:50]:
                ft = f.get('file_type', 'other')
                type_counts[ft] = type_counts.get(ft, 0) + 1
            type_dist = ", ".join(
                f"{FILE_TYPE_NAMES.get(k, k)} {v}个" for k, v in
                sorted(type_counts.items(), key=lambda x: -x[1])[:5]
            )

            # 时间范围（兼容 datetime 对象和字符串）
            from datetime import datetime as dt
            times = []
            for f in files[:50]:
                mt = f.get('modify_time')
                if mt:
                    if isinstance(mt, dt):
                        times.append(mt)
                    elif isinstance(mt, str):
                        try:
                            times.append(dt.strptime(mt[:19], "%Y-%m-%d %H:%M:%S"))
                        except ValueError:
                            pass
            time_range = "未获取到"
            if times:
                tmin = min(times).strftime("%Y-%m-%d")
                tmax = max(times).strftime("%Y-%m-%d")
                time_range = f"{tmin} ~ {tmax}" if tmin != tmax else tmin

            # 最大文件
            largest = max(files[:50], key=lambda f: f.get('file_size', 0))
            largest_file = f"{largest.get('file_name', '未知')} ({format_size(largest.get('file_size', 0))})"

            messages = build_summary_messages(
                search_query=search_query,
                total_count=count,
                total_size=format_size(total_bytes),
                type_distribution=type_dist,
                time_range=time_range,
                largest_file=largest_file,
            )
            result = self._backend.chat(messages, max_tokens=300, temperature=0.3)
            return ResponseParser.extract_plain_text(result.content)

        except Exception as e:
            logger.warning(f"AI 摘要生成失败: {e}")
            return None

    # ══════════════════════════════════════════════════════════════════════════
    # 文件问答（✨ 新增：追问 AI）
    # ══════════════════════════════════════════════════════════════════════════

    def answer_question(self, search_summary: str, question: str) -> Optional[str]:
        """基于搜索结果回答用户问题。

        Args:
            search_summary: 上文搜索结果摘要（可用 summarize_results 的输出）
            question: 用户追问

        Returns:
            回答文本，或 None
        """
        if not self.enabled:
            return None

        try:
            messages = build_qa_messages(search_summary, question)
            result = self._backend.chat(messages, max_tokens=400, temperature=0.3)
            return ResponseParser.extract_plain_text(result.content)
        except Exception as e:
            logger.warning(f"AI 问答失败: {e}")
            return None

    # ══════════════════════════════════════════════════════════════════════════
    # 文件智能描述（✨ 新增：右键菜单 AI 描述）
    # ══════════════════════════════════════════════════════════════════════════

    def describe_file(self, file_record: dict,
                      extra_metadata: str = "") -> Optional[str]:
        """对单个文件生成智能描述。

        Args:
            file_record: 文件数据库记录
            extra_metadata: 额外元数据文本（如 GPS、分辨率等）

        Returns:
            描述文本，或 None
        """
        if not self.enabled:
            return None

        try:
            messages = build_file_describe_messages(file_record, extra_metadata)
            result = self._backend.chat(messages, max_tokens=300, temperature=0.3)
            return ResponseParser.extract_plain_text(result.content)
        except Exception as e:
            logger.warning(f"AI 文件描述失败: {e}")
            return None

    # ══════════════════════════════════════════════════════════════════════════
    # 智能标签推荐（保持原有逻辑）
    # ══════════════════════════════════════════════════════════════════════════

    def recommend_tags(self, file_record: dict) -> Tuple[List[Tuple[str, float]], str]:
        """标签推荐: 优先 LLM，降级规则引擎。

        Returns:
            ([(tag, confidence), ...], source)
        """
        if self.enabled:
            try:
                messages = build_tag_messages(file_record)
                result = self._backend.chat(messages, max_tokens=300, temperature=0.1)

                safe, reason = OutputValidator.check_dangerous(result.content)
                if not safe:
                    logger.warning(f"LLM 标签输出不安全: {reason}")
                    tags = self.tag_recommender.recommend(file_record)
                    return tags, "rules"

                tags = ResponseParser.parse_tags(result.content)
                if tags:
                    logger.info(f"AI 标签推荐: {len(tags)} 个 ({result.latency_ms}ms)")
                    return tags, "ai"
                else:
                    logger.warning("AI 标签解析失败，降级规则引擎")

            except Exception as e:
                logger.warning(f"AI 标签调用失败: {e}，降级规则引擎")

        tags = self.tag_recommender.recommend(file_record)
        return tags, "rules"

    # ══════════════════════════════════════════════════════════════════════════
    # 意图解释增强（✨ 新增：更自然的自然语言解释）
    # ══════════════════════════════════════════════════════════════════════════

    def explain_search_intent(self, query: str) -> Optional[str]:
        """用自然语言解释用户的搜索意图（AI 生成的亲切解释）。

        Returns:
            "您想找最近一周的合同文档" 之类的句子，或 None
        """
        if not self.enabled:
            return None

        try:
            messages = build_intent_explanation_messages(query)
            result = self._backend.chat(messages, max_tokens=100, temperature=0.3)
            text = ResponseParser.extract_plain_text(result.content)
            return text if text else None
        except Exception as e:
            logger.warning(f"AI 意图解释失败: {e}")
            return None

    def explain_search(self, query: str) -> str:
        """解释搜索解析结果（增强版：优先用 AI 自然语言解释）"""
        # 先尝试 AI 自然语言意图解释
        ai_intent = self.explain_search_intent(query)
        if ai_intent:
            return ai_intent

        # 降级：用解析结果
        params, source = self.search(query)
        if not params:
            return "未能解析搜索条件"

        if source == "ai" and params.get('_explanation'):
            return params['_explanation']

        return self.search_parser.explain(query)

    # ══════════════════════════════════════════════════════════════════════════
    # 仪表盘洞察（Phase 1-1：AI 增强仪表盘）
    # ══════════════════════════════════════════════════════════════════════════

    def generate_dashboard_insights(self, total_files: int, total_size: str,
                                     dup_groups: int, wasted: str,
                                     type_distribution: str,
                                     top_dirs: str,
                                     monthly_trend: str) -> Optional[str]:
        """生成仪表盘智能洞察分析。

        Returns:
            洞察文本，或 None（AI 不可用时）
        """
        if not self.enabled:
            return None

        try:
            messages = build_dashboard_insight_messages(
                total_files=total_files,
                total_size=total_size,
                dup_groups=dup_groups,
                wasted=wasted,
                type_distribution=type_distribution,
                top_dirs=top_dirs,
                monthly_trend=monthly_trend,
            )
            result = self._backend.chat(messages, max_tokens=400, temperature=0.3)
            return ResponseParser.extract_plain_text(result.content)
        except Exception as e:
            logger.warning(f"AI 仪表盘洞察失败: {e}")
            return None

    # ══════════════════════════════════════════════════════════════════════════
    # 清理建议增强（Phase 1-2：AI 增强清理建议）
    # ══════════════════════════════════════════════════════════════════════════

    def enhance_cleanup_advice(self, categories_text: str) -> Optional[str]:
        """对规则引擎的清理分析结果做 AI 增强。

        Returns:
            增强后的建议文本，或 None
        """
        if not self.enabled:
            return None

        try:
            messages = build_cleanup_advice_messages(categories_text)
            result = self._backend.chat(messages, max_tokens=400, temperature=0.3)
            return ResponseParser.extract_plain_text(result.content)
        except Exception as e:
            logger.warning(f"AI 清理建议增强失败: {e}")
            return None

    # ══════════════════════════════════════════════════════════════════════════
    # 智能重命名（Phase 1-3：AI 重命名建议）
    # ══════════════════════════════════════════════════════════════════════════

    def suggest_rename(self, file_name: str, file_path: str,
                        file_type: str, file_size: str,
                        modify_time: str) -> Optional[list]:
        """为单个文件生成智能重命名建议。

        Returns:
            建议名称列表 ["建议1", "建议2", "建议3"]，或 None
        """
        if not self.enabled:
            return None

        try:
            messages = build_rename_suggestion_messages(
                file_name, file_path, file_type, file_size, modify_time
            )
            result = self._backend.chat(messages, max_tokens=300, temperature=0.3)
            suggestions = ResponseParser.parse_tags(result.content)
            # parse_tags 返回 [(name, confidence), ...]，取 name 部分
            if suggestions:
                return [s[0] for s in suggestions[:3]]
            # 尝试直接解析 rename JSON
            parsed = ResponseParser.parse_search(result.content)
            if parsed and 'name' in parsed:
                name_val = parsed['name']
                if isinstance(name_val, str) and '|' in name_val:
                    return name_val.split('|')[:3]
            return None
        except Exception as e:
            logger.warning(f"AI 重命名建议失败: {e}")
            return None

    # ══════════════════════════════════════════════════════════════════════════
    # 文件内容摘要（Phase 2-1：AI 文件内容阅读与摘要）
    # ══════════════════════════════════════════════════════════════════════════

    def summarize_file_content(self, file_name: str, file_path: str,
                                file_type: str, file_size: str,
                                modify_time: str,
                                file_content: str) -> Optional[str]:
        """基于文件实际内容生成摘要。

        Returns:
            内容摘要文本，或 None
        """
        if not self.enabled:
            return None

        try:
            # 截断过长内容
            if len(file_content) > 4000:
                file_content = file_content[:4000] + "\n...(内容已截断)"

            messages = build_content_summary_messages(
                file_name=file_name,
                file_path=file_path,
                file_type=file_type,
                file_size=file_size,
                modify_time=modify_time,
                file_content=file_content,
            )
            result = self._backend.chat(messages, max_tokens=500, temperature=0.3)
            return ResponseParser.extract_plain_text(result.content)
        except Exception as e:
            logger.warning(f"AI 文件内容摘要失败: {e}")
            return None

    # ══════════════════════════════════════════════════════════════════════════
    # 文件内容搜索（Phase 2-2：语义搜索增强）
    # ══════════════════════════════════════════════════════════════════════════

    def rank_by_relevance(self, query: str, file_summaries: list) -> Optional[list]:
        """根据用户查询意图，对文件列表按内容相关性排序。

        Args:
            query: 用户搜索意图
            file_summaries: [{"name": ..., "type": ..., "preview": ...}, ...]

        Returns:
            相关性排名列表 [{"name": ..., "relevance": "high|medium|low", "reason": "..."}, ...]
            或 None
        """
        if not self.enabled or not file_summaries:
            return None

        try:
            summaries_text = "\n".join(
                f"{i+1}. [{s['type']}] {s['name']} - {s.get('preview', '')[:200]}"
                for i, s in enumerate(file_summaries[:20])
            )

            messages = [
                {"role": "system",
                 "content": "你是一个文件搜索专家。根据用户的搜索意图，评估文件列表的相关性。"},
                {"role": "user",
                 "content": f"用户搜索意图: {query}\n\n"
                            f"文件列表:\n{summaries_text}\n\n"
                            f"请选出与用户意图最相关的文件（不超过8个），按以下JSON格式输出:\n"
                            f'{{"relevant": [{{"index": 1, "relevance": "high", "reason": "..."}}]}}'}
            ]
            result = self._backend.chat(messages, max_tokens=500, temperature=0.2)
            parsed = ResponseParser.parse_search(result.content)
            if parsed and isinstance(parsed, dict):
                return parsed.get('relevant', [])
            return None
        except Exception as e:
            logger.warning(f"AI 相关性排序失败: {e}")
            return None

    # ══════════════════════════════════════════════════════════════════════════
    # 分类规则建议（Phase 2-3：AI 分类规则自动生成）
    # ══════════════════════════════════════════════════════════════════════════

    def suggest_classify_rules(self, dir_sample: str) -> Optional[list]:
        """根据目录结构样本，建议自动分类规则。

        Returns:
            规则建议列表 [{"rule_name": ..., "keywords": ..., "match_type": ..., "reason": ...}, ...]
            或 None
        """
        if not self.enabled:
            return None

        try:
            messages = build_classify_rule_messages(dir_sample)
            result = self._backend.chat(messages, max_tokens=600, temperature=0.3)
            parsed = ResponseParser.parse_search(result.content)
            if parsed and isinstance(parsed, dict):
                return parsed.get('suggestions', [])
            return None
        except Exception as e:
            logger.warning(f"AI 分类规则建议失败: {e}")
            return None

    # ══════════════════════════════════════════════════════════════════════════
    # 通用对话（Phase 3：全新 AI 助手核心能力）
    # ══════════════════════════════════════════════════════════════════════════

    def chat(self, messages: list[dict],
             max_tokens: int = 1024,
             temperature: float = 0.3,
             tools: list = None) -> Optional[AIResult]:
        """通用对话 —— 支持工具定义。

        Args:
            messages: 消息列表 [{"role": ..., "content": ...}]
            max_tokens: 最大输出 token
            temperature: 温度
            tools: 可选 OpenAI 格式工具定义列表

        Returns:
            AIResult 或 None（AI 不可用时）
        """
        if not self.enabled:
            return None

        try:
            return self._backend.chat(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                tools=tools,
            )
        except Exception as e:
            logger.error(f"AI 通用对话失败: {e}")
            return None

    def chat_stream(self, messages: list[dict],
                    max_tokens: int = 1024,
                    temperature: float = 0.3,
                    tools: list = None) -> Generator[AIStreamChunk, None, None]:
        """流式通用对话 —— 逐 chunk 返回。

        Args:
            messages: 消息列表
            max_tokens: 最大输出 token
            temperature: 温度
            tools: 可选工具定义

        Yields:
            AIStreamChunk 增量数据块
        """
        if not self.enabled:
            yield AIStreamChunk(
                content_delta="[AI 未启用，请先配置 AI 模型]",
                is_done=True,
            )
            return

        try:
            yield from self._backend.chat_stream(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                tools=tools,
            )
        except Exception as e:
            logger.error(f"AI 流式对话失败: {e}")
            yield AIStreamChunk(
                content_delta=f"\n\n[AI 调用出错: {e}]",
                is_done=True,
            )

    def chat_with_tools(self, user_message: str,
                        conversation=None,  # AiConversation
                        system_prompt: str = None,
                        tool_registry=None,
                        working_directory: str = "",
                        stream_callback=None) -> str:
        """一次性工具调用循环：发用户消息 → LLM 自主调用工具 → 返回最终回复。

        这是最上层的便捷入口，自动处理：
        1. 创建/复用对话会话
        2. 添加系统消息
        3. 工具调用循环（最多 5 轮）
        4. 上下文压缩

        Args:
            user_message: 用户输入文本
            conversation: 可选的已有 AiConversation（传入则复用上下文）
            system_prompt: 自定义 system prompt
            tool_registry: 可选工具注册表（默认用内置的）
            working_directory: 当前工作目录
            stream_callback: 可选流式回调 callable(text)

        Returns:
            AI 的最终回复文本
        """
        from core.ai_chat import AiConversation, run_tool_loop
        from datetime import datetime

        tools = tool_registry or self.tool_registry

        # 创建或复用对话
        if conversation is None:
            from core.ai_prompts import GENERAL_ASSISTANT_SYSTEM_PROMPT
            if system_prompt is None:
                system_prompt = GENERAL_ASSISTANT_SYSTEM_PROMPT.format(
                    current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    working_directory=working_directory or "未知",
                )
            conversation = AiConversation(
                system_prompt=system_prompt,
                model=self.backend_model_name,
            )

        # 添加上下文信息
        user_content = user_message
        if working_directory and "[工作目录]" not in user_message:
            pass  # 上下文已在 system prompt 中

        conversation.add_user_message(user_content)

        # 执行工具调用循环
        response = run_tool_loop(
            conversation=conversation,
            backend=self._backend,
            tool_registry=tools,
            stream_callback=stream_callback,
        )

        # 自动生成标题
        if conversation.message_count <= 2:
            conversation.update_title(conversation.get_auto_title())

        return response
