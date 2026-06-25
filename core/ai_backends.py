"""
AI 后端抽象层 —— 通用 OpenAI 兼容协议后端。

支持所有兼容 OpenAI API 协议的提供商：
DeepSeek、通义千问、Moonshot、智谱、OpenAI 等。

支持功能：
- chat(): 同步对话（含 tools 参数）
- chat_stream(): 流式输出（渐进式返回）

用法:
    backend = OpenAICompatibleBackend(
        api_key="sk-xxx",
        base_url="https://api.deepseek.com/v1",
        model="deepseek-v4-flash"
    )
    result = backend.chat([{"role": "user", "content": "你好"}])
    for chunk in backend.chat_stream([{"role": "user", "content": "你好"}]):
        print(chunk)
"""

import json
import time
from typing import Optional, Generator
from dataclasses import dataclass, field

import httpx

from utils.logger import logger


@dataclass
class AIResult:
    """LLM 调用结果"""
    content: str                          # 模型返回的文本
    model: str                            # 使用的模型名
    tokens_in: int = 0                    # 输入 token
    tokens_out: int = 0                   # 输出 token
    latency_ms: int = 0                   # 延迟毫秒
    tool_calls: Optional[list] = None     # 工具调用请求（function calling）


@dataclass
class AIStreamChunk:
    """流式输出的单个数据块"""
    content_delta: str = ""               # 增量文本
    is_done: bool = False                 # 是否最后一帧
    model: str = ""                       # 使用的模型
    tokens_in: int = 0                    # 输入 token（最后一帧才有）
    tokens_out: int = 0                   # 输出 token（最后一帧才有）
    tool_calls: Optional[list] = None     # 累积的工具调用请求


class OpenAICompatibleBackend:
    """通用 OpenAI 兼容协议后端 —— 支持任意兼容的 API 提供商"""

    def __init__(self, api_key: str, base_url: str, model: str,
                 timeout: float = 20.0):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=httpx.Timeout(self.timeout),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
            )
        return self._client

    def chat(self, messages: list[dict], max_tokens: int = 512,
             temperature: float = 0.1,
             response_format: Optional[dict] = None,
             tools: Optional[list] = None) -> AIResult:
        """发送对话请求，返回结构化结果。支持 function calling。

        Args:
            messages: [{"role": "user"/"assistant"/"system"/"tool", "content": "..."}]
            max_tokens: 最大输出 token
            temperature: 温度 (0-2)，越低越确定
            response_format: 可选 {"type": "json_object"} 强制 JSON 输出
            tools: 可选，OpenAI 格式的工具定义列表
        """
        t0 = time.time()
        body = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if response_format:
            body["response_format"] = response_format
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        try:
            resp = self.client.post(
                f"{self.base_url}/chat/completions",
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

            choice = data["choices"][0]
            msg = choice["message"]
            content = msg.get("content") or ""
            finish_reason = choice.get("finish_reason", "")
            usage = data.get("usage", {})
            latency = int((time.time() - t0) * 1000)

            # 提取 tool_calls
            tool_calls = None
            raw_tool_calls = msg.get("tool_calls")
            if raw_tool_calls:
                tool_calls = []
                for tc in raw_tool_calls:
                    tool_calls.append({
                        "id": tc.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": tc.get("function", {}).get("name", ""),
                            "arguments": tc.get("function", {}).get("arguments", "{}"),
                        }
                    })

            result = AIResult(
                content=content.strip(),
                model=data.get("model", self.model),
                tokens_in=usage.get("prompt_tokens", 0),
                tokens_out=usage.get("completion_tokens", 0),
                latency_ms=latency,
                tool_calls=tool_calls,
            )
            logger.info(
                f"AI API: req_model={self.model}, resp_model={result.model}, "
                f"tokens={result.tokens_in}+{result.tokens_out}, "
                f"latency={latency}ms, tool_calls={bool(tool_calls)}"
            )
            return result

        except httpx.HTTPStatusError as e:
            logger.error(f"AI API HTTP {e.response.status_code}: {e.response.text[:200]}")
            raise
        except httpx.TimeoutException:
            logger.error(f"AI API 超时 ({self.timeout}s)")
            raise
        except Exception as e:
            logger.error(f"AI API 异常: {e}")
            raise

    def chat_stream(self, messages: list[dict], max_tokens: int = 1024,
                    temperature: float = 0.3,
                    tools: Optional[list] = None) -> Generator[AIStreamChunk, None, None]:
        """流式对话请求 —— 逐 chunk 返回增量文本。

        Args:
            messages: 消息列表
            max_tokens: 最大输出 token
            temperature: 温度
            tools: 可选工具定义

        Yields:
            AIStreamChunk: 每次 yield 一个增量数据块
        """
        t0 = time.time()
        body = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        accumulated_content = ""
        accumulated_tool_calls: dict = {}  # index → {id, name, arguments}
        final_tokens_in = 0
        final_tokens_out = 0

        try:
            with self.client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=body,
            ) as resp:
                resp.raise_for_status()

                for line in resp.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue

                    data_str = line[6:]  # 去掉 "data: " 前缀
                    if data_str.strip() == "[DONE]":
                        break

                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    choices = data.get("choices", [])
                    if not choices:
                        continue

                    choice = choices[0]
                    delta = choice.get("delta", {})

                    # 收集 usage（最后一帧才有）
                    usage = data.get("usage", {})
                    if usage:
                        final_tokens_in = usage.get("prompt_tokens", 0)
                        final_tokens_out = usage.get("completion_tokens", 0)

                    # 增量文本
                    content_delta = delta.get("content") or ""
                    if content_delta:
                        accumulated_content += content_delta
                        yield AIStreamChunk(
                            content_delta=content_delta,
                            is_done=False,
                            model=data.get("model", self.model),
                        )

                    # 增量 tool_calls
                    tc_delta = delta.get("tool_calls")
                    if tc_delta:
                        for tc in tc_delta:
                            idx = tc.get("index", 0)
                            if idx not in accumulated_tool_calls:
                                accumulated_tool_calls[idx] = {
                                    "id": tc.get("id", ""),
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""},
                                }
                            entry = accumulated_tool_calls[idx]
                            if tc.get("id"):
                                entry["id"] = tc["id"]
                            func = tc.get("function", {})
                            if func.get("name"):
                                entry["function"]["name"] += func["name"]
                            if func.get("arguments"):
                                entry["function"]["arguments"] += func["arguments"]

            # 最后一帧：累计结果
            latency = int((time.time() - t0) * 1000)
            tool_calls = list(accumulated_tool_calls.values()) if accumulated_tool_calls else None

            logger.info(
                f"AI API Stream: model={self.model}, "
                f"tokens={final_tokens_in}+{final_tokens_out}, "
                f"latency={latency}ms, content_len={len(accumulated_content)}, "
                f"tool_calls={bool(tool_calls)}"
            )

            yield AIStreamChunk(
                content_delta="",
                is_done=True,
                model=self.model,
                tokens_in=final_tokens_in,
                tokens_out=final_tokens_out,
                tool_calls=tool_calls,
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"AI API Stream HTTP {e.response.status_code}: {e.response.text[:200]}")
            raise
        except httpx.TimeoutException:
            logger.error(f"AI API Stream 超时 ({self.timeout}s)")
            raise
        except Exception as e:
            logger.error(f"AI API Stream 异常: {e}")
            raise

    def stream_to_complete(self, messages: list[dict],
                           on_chunk=None,  # callable(content_delta: str)
                           **kwargs) -> AIResult:
        """便捷方法：流式接收但返回完整的 AIResult。

        Args:
            messages: 消息列表
            on_chunk: 可选，每收到文本增量时回调
            **kwargs: 传递给 chat_stream() 的参数

        Returns:
            AIResult: 包含完整内容和 tool_calls 的最终结果
        """
        full_content = ""
        tool_calls = None
        model = self.model
        t_in = t_out = 0

        for chunk in self.chat_stream(messages, **kwargs):
            if chunk.content_delta:
                full_content += chunk.content_delta
                if on_chunk:
                    on_chunk(chunk.content_delta)
            if chunk.is_done:
                model = chunk.model or model
                t_in = chunk.tokens_in
                t_out = chunk.tokens_out
                tool_calls = chunk.tool_calls

        return AIResult(
            content=full_content.strip(),
            model=model,
            tokens_in=t_in,
            tokens_out=t_out,
            tool_calls=tool_calls,
        )


# 向后兼容别名
DeepSeekBackend = OpenAICompatibleBackend
