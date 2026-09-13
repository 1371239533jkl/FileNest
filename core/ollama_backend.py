"""
Ollama 本地 AI 后端 —— 基于 OpenAICompatibleBackend 的轻量封装。

Ollama 原生兼容 OpenAI API（/v1 路径），所以大部分逻辑直接复用。
这里只处理 Ollama 特有的：
- 无需 api_key（填 "ollama" 占位即可）
- 默认 base_url: http://localhost:11434/v1
- /api/tags 列出本地已安装模型
- /api/pull 拉取模型（异步）
- 健康检测走 /api/tags 而非 /v1/models

用法:
    backend = OllamaBackend(model="qwen2.5:7b-instruct")
    result = backend.chat([{"role": "user", "content": "你好"}])
    models = OllamaBackend.list_local_models()
"""

from typing import Optional

import httpx

from core.ai_backends import OpenAICompatibleBackend, AIResult
from utils.logger import logger


DEFAULT_OLLAMA_URL = "http://localhost:11434"


class OllamaBackend(OpenAICompatibleBackend):
    """Ollama 本地模型后端 —— 兼容 OpenAI API 协议。"""

    def __init__(self, model: str, base_url: str = DEFAULT_OLLAMA_URL,
                 timeout: float = 60.0):
        # Ollama 不需要 api_key，但 OpenAICompatibleBackend 要求传，填占位符
        # 实际请求时 Authorization header 会被带上 "Bearer ollama"，Ollama 会忽略
        super().__init__(
            api_key="ollama",
            base_url=f"{base_url.rstrip('/')}/v1",
            model=model,
            timeout=timeout,
        )
        self.ollama_base = base_url.rstrip('/')

    @staticmethod
    def list_local_models(base_url: str = DEFAULT_OLLAMA_URL) -> list[dict]:
        """列出 Ollama 本地已安装的所有模型。

        Returns:
            [{"name": "qwen2.5:7b", "size": 1234567, "modified_at": "...",
              "details": {"family": "qwen2", "parameter_size": "7B"}}, ...]
            失败返回空列表
        """
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(f"{base_url.rstrip('/')}/api/tags")
                resp.raise_for_status()
                data = resp.json()
                return data.get("models", [])
        except Exception as e:
            logger.debug(f"Ollama 列模型失败: {e}")
            return []

    @staticmethod
    def is_available(base_url: str = DEFAULT_OLLAMA_URL) -> tuple[bool, str]:
        """检测 Ollama 服务是否运行。

        Returns:
            (是否可用, 描述)
        """
        try:
            with httpx.Client(timeout=3.0) as client:
                resp = client.get(f"{base_url.rstrip('/')}/api/tags")
                if resp.status_code == 200:
                    models = resp.json().get("models", [])
                    return True, f"Ollama 运行中，已安装 {len(models)} 个模型"
                return False, f"HTTP {resp.status_code}"
        except httpx.ConnectError:
            return False, "Ollama 未启动或地址不可达"
        except Exception as e:
            return False, str(e)[:100]

    def health_check(self) -> tuple[bool, str]:
        """覆盖父类：用 Ollama 原生 /api/tags 检测。"""
        return OllamaBackend.is_available(self.ollama_base)

    def pull_model(self, model: str) -> bool:
        """触发拉取模型（异步，仅触发，不等待完成）。

        Returns:
            True 表示请求已发出，实际拉取在后台进行
        """
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    f"{self.ollama_base}/api/pull",
                    json={"name": model, "stream": False},
                )
                resp.raise_for_status()
                logger.info(f"Ollama 开始拉取模型: {model}")
                return True
        except Exception as e:
            logger.error(f"Ollama 拉取模型失败 {model}: {e}")
            return False
