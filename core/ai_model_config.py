"""
AI 模型配置管理器 —— 支持多提供商、自定义模型。

配置存储为项目根目录的 ai_models.json 文件。
"""

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Optional, List

from utils.logger import logger

# 配置文件路径
_CONFIG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AI_MODELS_FILE = os.path.join(_CONFIG_DIR, "ai_models.json")

# 内置默认提供商配置（作为模板参考）
BUILTIN_PROVIDERS = {
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "models": "deepseek-chat,deepseek-v4-flash,deepseek-reasoner",
        "default_model": "deepseek-chat",
        "timeout": 20,
    },
    "qwen": {
        "name": "通义千问 (Qwen)",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": "qwen-plus,qwen-max,qwen-turbo",
        "default_model": "qwen-plus",
        "timeout": 20,
    },
    "moonshot": {
        "name": "Moonshot (月之暗面)",
        "base_url": "https://api.moonshot.cn/v1",
        "models": "moonshot-v1-8k,moonshot-v1-32k,moonshot-v1-128k",
        "default_model": "moonshot-v1-8k",
        "timeout": 20,
    },
    "zhipu": {
        "name": "智谱 AI (GLM)",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": "glm-4-plus,glm-4-flash,glm-4-air",
        "default_model": "glm-4-flash",
        "timeout": 20,
    },
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models": "gpt-4o,gpt-4o-mini,gpt-3.5-turbo",
        "default_model": "gpt-4o-mini",
        "timeout": 20,
    },
    "siliconflow": {
        "name": "硅基流动 (免费)",
        "base_url": "https://api.siliconflow.cn/v1",
        "models": "deepseek-ai/DeepSeek-V3,Pro/deepseek-ai/DeepSeek-R1,Qwen/Qwen2.5-7B-Instruct",
        "default_model": "deepseek-ai/DeepSeek-V3",
        "timeout": 60,
    },
}


@dataclass
class AIModelProvider:
    """单个 AI 提供商配置"""
    provider_id: str                          # 唯一标识，如 "deepseek"
    name: str                                 # 显示名，如 "DeepSeek"
    base_url: str                             # API 端点
    api_key: str = ""                         # API 密钥
    model: str = ""                           # 当前使用的模型
    models: str = ""                          # 可用模型列表（逗号分隔）
    timeout: float = 60.0                     # 超时秒数

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "AIModelProvider":
        return cls(
            provider_id=d.get("provider_id", ""),
            name=d.get("name", ""),
            base_url=d.get("base_url", ""),
            api_key=d.get("api_key", ""),
            model=d.get("model", ""),
            models=d.get("models", ""),
            timeout=d.get("timeout", 60),
        )


class AIModelConfigManager:
    """AI 模型配置管理器：加载 / 保存 / CRUD"""

    def __init__(self, config_path: str = AI_MODELS_FILE):
        self._config_path = config_path
        self._data: dict = {"active_provider": "", "providers": {}}
        self._load()

    # ── 文件读写 ──

    def _load(self):
        """从 JSON 文件加载配置"""
        if os.path.exists(self._config_path):
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                logger.info(f"已加载 AI 模型配置: {len(self._data.get('providers', {}))} 个提供商")
            except Exception as e:
                logger.warning(f"加载 AI 模型配置失败: {e}，使用空配置")
                self._data = {"active_provider": "", "providers": {}}
        else:
            self._data = {"active_provider": "", "providers": {}}

    def _save(self):
        """保存配置到 JSON 文件"""
        try:
            os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            logger.debug("AI 模型配置已保存")
        except Exception as e:
            logger.error(f"保存 AI 模型配置失败: {e}")

    # ── 查询 ──

    @property
    def active_provider_id(self) -> str:
        return self._data.get("active_provider", "")

    def get_active(self) -> Optional[AIModelProvider]:
        """获取当前激活的提供商配置"""
        pid = self.active_provider_id
        if not pid:
            return None
        return self.get_provider(pid)

    def get_provider(self, provider_id: str) -> Optional[AIModelProvider]:
        """获取指定提供商"""
        pdata = self._data.get("providers", {}).get(provider_id)
        if not pdata:
            return None
        return AIModelProvider.from_dict(pdata)

    def list_providers(self) -> List[AIModelProvider]:
        """列出所有提供商"""
        return [
            AIModelProvider.from_dict(p)
            for p in self._data.get("providers", {}).values()
        ]

    def provider_count(self) -> int:
        return len(self._data.get("providers", {}))

    # ── 修改 ──

    def add_provider(self, provider: AIModelProvider) -> bool:
        """添加或更新提供商"""
        pid = provider.provider_id
        if not pid:
            logger.error("provider_id 不能为空")
            return False

        # ponytail: 写前重新加载最新文件，避免多个 manager 实例各自缓存
        # 旧 _data、写入时互相覆盖（症状：设置里保存的 api_key 莫名消失）。
        self._load()

        providers = self._data.setdefault("providers", {})
        providers[pid] = provider.to_dict()

        # 如果是第一个提供商，自动设为激活
        if not self._data.get("active_provider"):
            self._data["active_provider"] = pid

        self._save()
        logger.info(f"已{'更新' if pid in providers else '添加'} AI 提供商: {provider.name} ({pid})")
        return True

    def delete_provider(self, provider_id: str) -> bool:
        """删除提供商"""
        providers = self._data.get("providers", {})
        if provider_id not in providers:
            return False

        del providers[provider_id]

        # 如果删除的是当前激活的，清除激活状态
        if self._data.get("active_provider") == provider_id:
            # 切换到剩余的第一个，或清空
            remaining = list(providers.keys())
            self._data["active_provider"] = remaining[0] if remaining else ""

        self._save()
        logger.info(f"已删除 AI 提供商: {provider_id}")
        return True

    def set_active(self, provider_id: str) -> bool:
        """设置激活的提供商"""
        # ponytail: 写前重新加载最新文件，防止覆盖其他实例刚保存的修改
        self._load()
        if provider_id and provider_id not in self._data.get("providers", {}):
            logger.warning(f"提供商不存在: {provider_id}")
            return False
        self._data["active_provider"] = provider_id
        self._save()
        logger.info(f"已切换 AI 提供商: {provider_id}")
        return True

    # ── 预置模板 ──

    # ── 上下文窗口查询 ──

    # 模型上下文窗口大小估算（字符数），用于 UI 指示器和压缩阈值
    # key 为小写子串匹配，按匹配优先级排列
    _CONTEXT_LIMITS: list = [
        # 128K 级别
        ("128k", 128000), ("moonshot-v1-128", 128000), ("gpt-4o", 128000),
        ("gpt-4-turbo", 128000), ("claude-3", 200000), ("claude-3.5", 200000),
        ("glm-4", 128000),
        # 64K 级别
        ("deepseek", 64000), ("deepseek-v4", 64000), ("deepseek-r1", 64000),
        ("deepseek-reasoner", 64000), ("64k", 64000),
        # 32K 级别
        ("qwen-plus", 32000), ("qwen-max", 32000), ("qwen2.5-7b", 32000),
        ("32k", 32000), ("qwen2.5-32b", 32000), ("qwen2.5-72b", 32000),
        # 16K 级别
        ("gpt-3.5", 16000), ("16k", 16000),
        # 8K 级别（兜底）
        ("8k", 8000), ("qwen-turbo", 8000), ("qwen2.5-1.5b", 8000),
    ]

    @classmethod
    def get_model_context_limit(cls, model_name: str) -> int:
        """根据模型名返回估算的上下文窗口大小（字符数），未知模型默认 8K"""
        name_lower = model_name.lower()
        for pattern, limit in cls._CONTEXT_LIMITS:
            if pattern in name_lower:
                return limit
        return 8000  # 未知模型：保守 8K

    # ── 预置模板 ──

    def add_builtin_template(self, provider_id: str) -> Optional[AIModelProvider]:
        """添加系统内置提供商模板（不含 API Key）"""
        template = BUILTIN_PROVIDERS.get(provider_id)
        if not template:
            return None

        provider = AIModelProvider(
            provider_id=provider_id,
            name=template["name"],
            base_url=template["base_url"],
            api_key="",
            model=template.get("default_model", ""),
            models=template.get("models", ""),
            timeout=template.get("timeout", 20),
        )
        self.add_provider(provider)
        return provider

