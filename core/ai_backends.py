"""
AI 后端抽象层 —— 通用 OpenAI 兼容协议后端。

支持所有兼容 OpenAI API 协议的提供商：
DeepSeek、通义千问、Moonshot、智谱、OpenAI 等。

用法:
    backend = OpenAICompatibleBackend(
        api_key="sk-xxx",
        base_url="https://api.deepseek.com/v1",
        model="deepseek-v4-flash"
    )
    result = backend.chat([{"role": "user", "content": "你好"}])
"""

import json
import time
from typing import Optional
from dataclasses import dataclass

import httpx

from utils.logger import logger


@dataclass
class AIResult:
    """LLM 调用结果"""
    content: str          # 模型返回的文本
    model: str            # 使用的模型名
    tokens_in: int = 0    # 输入 token
    tokens_out: int = 0   # 输出 token
    latency_ms: int = 0   # 延迟毫秒


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
             response_format: Optional[dict] = None) -> AIResult:
        """发送对话请求，返回结构化结果。

        Args:
            messages: [{"role": "user"/"assistant"/"system", "content": "..."}]
            max_tokens: 最大输出 token
            temperature: 温度 (0-2)，越低越确定
            response_format: 可选 {"type": "json_object"} 强制 JSON 输出
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

        try:
            resp = self.client.post(
                f"{self.base_url}/chat/completions",
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

            choice = data["choices"][0]
            content = choice["message"]["content"]
            usage = data.get("usage", {})
            latency = int((time.time() - t0) * 1000)

            result = AIResult(
                content=content.strip(),
                model=data.get("model", self.model),
                tokens_in=usage.get("prompt_tokens", 0),
                tokens_out=usage.get("completion_tokens", 0),
                latency_ms=latency,
            )
            logger.info(
                f"AI API: req_model={self.model}, resp_model={result.model}, "
                f"tokens={result.tokens_in}+{result.tokens_out}, "
                f"latency={latency}ms"
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


# 向后兼容别名
DeepSeekBackend = OpenAICompatibleBackend
