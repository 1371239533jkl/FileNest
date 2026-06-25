"""
AI 多轮对话管理器 —— 支持上下文记忆、工具调用循环、会话持久化。

核心类 AiConversation 负责：
1. 维护完整对话历史（system/user/assistant/tool 角色）
2. 自动工具调用循环（LLM 请求工具 → 执行 → 结果注入 → 持续推理）
3. 上下文窗口管理（超限时自动压缩早期消息）
4. 会话保存/加载

用法:
    conv = AiConversation(system_prompt="你是一个助手", model="deepseek-chat")
    conv.add_user_message("帮我找大于100MB的图片")
    response = layer.chat_with_tools(conv, tool_registry)
"""

import json
import os
import time
from typing import Optional, List
from dataclasses import dataclass, field

from utils.logger import logger


# ══════════════════════════════════════════════════════════════════════════════
# 会话数据结构
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ConversationMessage:
    """单条对话消息"""
    role: str                              # system / user / assistant / tool
    content: str                           # 文本内容
    tool_calls: Optional[list] = None      # assistant 角色的工具调用请求
    tool_call_id: Optional[str] = None     # tool 角色的调用 ID
    name: Optional[str] = None             # 工具名（tool 角色）


@dataclass
class SessionMeta:
    """会话元数据"""
    session_id: str                        # 唯一标识
    title: str                             # 会话标题
    model: str                             # 使用的模型
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    message_count: int = 0


# ══════════════════════════════════════════════════════════════════════════════
# 多轮对话管理器
# ══════════════════════════════════════════════════════════════════════════════

class AiConversation:
    """AI 多轮对话会话

    维护完整的对话历史，支持自动上下文压缩和会话持久化。
    """

    MAX_CONTEXT_TOKENS_ESTIMATE = 8000     # 估算的上下文窗口大小（字符数）
    COMPRESS_THRESHOLD = 0.8               # 达到 80% 时触发压缩

    def __init__(self, system_prompt: str = "", model: str = "",
                 session_id: str = None, title: str = ""):
        self.model = model
        self.meta = SessionMeta(
            session_id=session_id or f"session_{int(time.time())}_{os.urandom(4).hex()}",
            title=title or "新对话",
            model=model,
        )
        self._messages: List[ConversationMessage] = []
        if system_prompt:
            self._messages.append(ConversationMessage(
                role="system",
                content=system_prompt,
            ))

    # ── 消息管理 ──

    def add_message(self, role: str, content: str,
                    tool_calls: list = None,
                    tool_call_id: str = None,
                    name: str = None) -> None:
        """添加一条消息到对话历史"""
        msg = ConversationMessage(
            role=role,
            content=content,
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,
            name=name,
        )
        self._messages.append(msg)
        self.meta.message_count = len([m for m in self._messages if m.role != "system"])
        self.meta.updated_at = time.time()

    def add_system_message(self, content: str) -> None:
        """添加/替换系统消息"""
        # 移除已有的 system 消息
        self._messages = [m for m in self._messages if m.role != "system"]
        self._messages.insert(0, ConversationMessage(role="system", content=content))

    def add_user_message(self, content: str) -> None:
        """添加用户消息"""
        self.add_message("user", content)

    def add_assistant_message(self, content: str, tool_calls: list = None) -> None:
        """添加助手回复"""
        self.add_message("assistant", content, tool_calls=tool_calls)

    def add_tool_result(self, tool_call_id: str, tool_name: str, result: str) -> None:
        """添加工具执行结果"""
        self.add_message(
            "tool",
            result,
            tool_call_id=tool_call_id,
            name=tool_name,
        )

    # ── 上下文查询 ──

    def get_messages(self) -> List[ConversationMessage]:
        """获取当前所有消息"""
        return list(self._messages)

    def get_api_messages(self) -> list[dict]:
        """转为 OpenAI API 格式的消息列表"""
        result = []
        for m in self._messages:
            entry = {"role": m.role, "content": m.content}
            if m.tool_calls:
                entry["tool_calls"] = m.tool_calls
            if m.tool_call_id:
                entry["tool_call_id"] = m.tool_call_id
            if m.name:
                entry["name"] = m.name
            result.append(entry)
        return result

    def get_user_messages(self) -> List[ConversationMessage]:
        """获取所有用户消息"""
        return [m for m in self._messages if m.role == "user"]

    def get_last_assistant_message(self) -> Optional[ConversationMessage]:
        """获取最后一条助手消息"""
        for m in reversed(self._messages):
            if m.role == "assistant":
                return m
        return None

    @property
    def message_count(self) -> int:
        return self.meta.message_count

    # ── 上下文窗口管理 ──

    def estimate_context_size(self) -> int:
        """估算当前上下文的总字符数"""
        total = 0
        for m in self._messages:
            total += len(m.content) if m.content else 0
            if m.tool_calls:
                total += len(json.dumps(m.tool_calls, ensure_ascii=False))
        return total

    def summarize_if_needed(self) -> bool:
        """如果上下文接近窗口上限，自动压缩早期消息。

        压缩策略：保留 system 消息 + 最近 6 轮对话，将其余内容用 AI 摘要替代。
        注意：此处仅做占位压缩（将早期 user/assistant 消息合并），
        实际 AI 摘要功能需要在 UI 层触发。

        Returns:
            True 表示执行了压缩
        """
        size = self.estimate_context_size()
        threshold = int(self.MAX_CONTEXT_TOKENS_ESTIMATE * self.COMPRESS_THRESHOLD)

        if size < threshold:
            return False

        logger.info(f"上下文超限 ({size}/{self.MAX_CONTEXT_TOKENS_ESTIMATE})，执行压缩...")

        # 保留 system + 最近 6 条 user/assistant 消息
        system_msgs = [m for m in self._messages if m.role == "system"]
        non_system = [m for m in self._messages if m.role != "system"]

        if len(non_system) <= 6:
            return False  # 消息太少，不压缩

        # 将早期消息替换为摘要占位
        early = non_system[:-6]
        recent = non_system[-6:]

        # 收集早期对话的要点
        early_summary_parts = []
        for m in early:
            if m.role == "user":
                early_summary_parts.append(f"用户问: {m.content[:100]}")
            elif m.role == "assistant" and m.content:
                early_summary_parts.append(f"助手答: {m.content[:100]}")
            elif m.role == "tool":
                early_summary_parts.append(f"[工具 {m.name} 返回结果]")

        summary_text = f"[早期对话摘要] 之前的对话涉及: {'; '.join(early_summary_parts[:10])}"

        self._messages = system_msgs + [
            ConversationMessage(role="user", content=summary_text),
            ConversationMessage(role="assistant",
                              content="明白了，我已记住之前的讨论。请继续。")
        ] + recent

        logger.info(f"压缩完成: {len(early)} 条消息 → 2 条摘要")
        return True

    def trim_last_tool_loop(self) -> None:
        """移除最后一轮不完整的工具调用循环（用于错误恢复）"""
        # 从末尾找最近一次 assistant + tool 组合
        idx = len(self._messages) - 1
        while idx >= 0:
            m = self._messages[idx]
            if m.role == "tool":
                # 移除 tool 及其前面的 assistant（含 tool_calls）
                self._messages = self._messages[:idx]
                idx = len(self._messages) - 1
            elif m.role == "assistant" and m.tool_calls:
                self._messages = self._messages[:idx]
                break
            idx -= 1

    # ── 会话持久化 ──

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "meta": {
                "session_id": self.meta.session_id,
                "title": self.meta.title,
                "model": self.meta.model,
                "created_at": self.meta.created_at,
                "updated_at": self.meta.updated_at,
                "message_count": self.meta.message_count,
            },
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "tool_calls": m.tool_calls,
                    "tool_call_id": m.tool_call_id,
                    "name": m.name,
                }
                for m in self._messages
            ]
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AiConversation":
        """从字典恢复会话"""
        meta = data.get("meta", {})
        conv = cls(
            session_id=meta.get("session_id", ""),
            title=meta.get("title", "恢复的对话"),
            model=meta.get("model", ""),
        )
        conv.meta.created_at = meta.get("created_at", time.time())
        conv.meta.updated_at = meta.get("updated_at", time.time())
        conv.meta.message_count = meta.get("message_count", 0)

        for m_data in data.get("messages", []):
            conv._messages.append(ConversationMessage(
                role=m_data.get("role", "user"),
                content=m_data.get("content", ""),
                tool_calls=m_data.get("tool_calls"),
                tool_call_id=m_data.get("tool_call_id"),
                name=m_data.get("name"),
            ))

        return conv

    def save(self, directory: str) -> str:
        """保存会话到文件"""
        os.makedirs(directory, exist_ok=True)
        filepath = os.path.join(directory, f"{self.meta.session_id}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"会话已保存: {filepath}")
        return filepath

    @classmethod
    def load(cls, filepath: str) -> "AiConversation":
        """从文件加载会话"""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        conv = cls.from_dict(data)
        logger.info(f"会话已加载: {filepath} ({conv.message_count} 条消息)")
        return conv

    @classmethod
    def list_sessions(cls, directory: str) -> List[SessionMeta]:
        """列出目录中的所有会话"""
        if not os.path.exists(directory):
            return []
        sessions = []
        for filename in os.listdir(directory):
            if filename.endswith(".json"):
                filepath = os.path.join(directory, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    meta = data.get("meta", {})
                    sessions.append(SessionMeta(
                        session_id=meta.get("session_id", filename[:-5]),
                        title=meta.get("title", "未命名"),
                        model=meta.get("model", ""),
                        created_at=meta.get("created_at", 0),
                        updated_at=meta.get("updated_at", 0),
                        message_count=meta.get("message_count", 0),
                    ))
                except Exception as e:
                    logger.warning(f"跳过损坏的会话文件 {filename}: {e}")

        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions

    # ── 工具调用辅助 ──

    def has_pending_tool_calls(self) -> bool:
        """检查最后一条助手消息是否有未处理的工具调用"""
        last = self.get_last_assistant_message()
        return last is not None and bool(last.tool_calls)

    def get_auto_title(self) -> str:
        """根据第一条用户消息自动生成标题"""
        for m in self._messages:
            if m.role == "user" and m.content.strip():
                title = m.content.strip()[:30]
                return title if len(title) < 30 else title + "…"
        return "新对话"

    def update_title(self, title: str) -> None:
        """更新会话标题"""
        self.meta.title = title


# ══════════════════════════════════════════════════════════════════════════════
# 工具调用循环引擎
# ══════════════════════════════════════════════════════════════════════════════

MAX_TOOL_LOOP_ROUNDS = 5  # 最多执行 5 轮工具调用


def run_tool_loop(
    conversation: AiConversation,
    backend,  # OpenAICompatibleBackend
    tool_registry,  # ToolRegistry
    stream_callback=None,  # callable(chunk_text) 流式输出回调
) -> str:
    """执行工具调用循环：LLM 请求工具 → 执行 → 注入结果 → 重复直到不再请求工具。

    Args:
        conversation: 对话会话（用户消息已添加）
        backend: AI 后端实例
        tool_registry: 工具注册表
        stream_callback: 可选，逐 chunk 回调函数

    Returns:
        LLM 的最终文本回复
    """
    tool_schemas = tool_registry.get_tool_schemas() if tool_registry else []
    final_response = ""

    for round_idx in range(MAX_TOOL_LOOP_ROUNDS):
        try:
            result = backend.chat(
                messages=conversation.get_api_messages(),
                max_tokens=1024,
                temperature=0.3,
                tools=tool_schemas if tool_schemas else None,
            )
        except Exception as e:
            logger.error(f"工具循环第 {round_idx + 1} 轮 LLM 调用失败: {e}")
            error_msg = f"\n\n[AI 调用出错：{e}]"
            if stream_callback:
                stream_callback(error_msg)
            final_response += error_msg
            break

        # 检查 LLM 是否请求工具调用
        tool_calls = result.tool_calls if hasattr(result, 'tool_calls') else getattr(result, 'tool_calls', None)

        if not tool_calls:
            # 没有工具调用请求 → 这是最终回复
            final_response = result.content
            conversation.add_assistant_message(result.content)
            if stream_callback:
                stream_callback(result.content)
            break

        # 记录 assistant 的工具调用请求
        conversation.add_assistant_message(
            content=result.content or "",
            tool_calls=tool_calls,
        )

        # 执行每个工具并注入结果
        for tc in tool_calls:
            tc_id = tc.get("id", f"call_{round_idx}")
            tc_func = tc.get("function", {})
            tc_name = tc_func.get("name", "")
            tc_args_str = tc_func.get("arguments", "{}")

            # 解析参数
            try:
                tc_args = json.loads(tc_args_str) if isinstance(tc_args_str, str) else tc_args_str
            except json.JSONDecodeError:
                tc_args = {}

            # 通知 UI 层
            if stream_callback:
                stream_callback(f"\n\n🔧 正在使用工具: **{tc_name}**...\n")

            # 执行工具
            tool_result = tool_registry.execute(tc_name, tc_args)

            # 注入结果到对话
            conversation.add_tool_result(tc_id, tc_name, tool_result)

    else:
        # 达到最大循环轮数
        logger.warning(f"工具调用达到最大轮数 {MAX_TOOL_LOOP_ROUNDS}，强制终止")
        conversation.add_assistant_message(
            "我已执行了多轮工具调用。如果你需要更深入的分析，请告诉我具体需求。"
        )
        final_response = conversation.get_last_assistant_message().content
        if stream_callback:
            stream_callback(final_response)

    return final_response
