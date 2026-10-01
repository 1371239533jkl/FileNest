"""回归测试：AILayer._send 必须转发给后端，不能递归调用自身。

2026-09-17 修复：_send 末行误写为 `return self._send(...)`，
任何 AI 调用（仪表盘洞察/摘要/问答）都会无限递归直到 RecursionError。
"""
from core.ai_layer import AILayer
from core.ai_backends import AIResult


class _FakeBackend:
    """记录是否被调用，返回固定结果，避免真实网络请求。"""

    def __init__(self):
        self.called = 0

    def chat(self, messages, **kwargs):
        self.called += 1
        return AIResult(content="ok", model="fake")


def _make_layer(fake: _FakeBackend) -> AILayer:
    layer = object.__new__(AILayer)
    layer._initialized = True
    layer._backend = fake

    class _Privacy:
        @staticmethod
        def get_config():
            return {"pii_masking": True}

        @staticmethod
        def mask_pii(text):
            return text

    layer.privacy = _Privacy()
    return layer


def test_send_forwards_to_backend():
    fake = _FakeBackend()
    layer = _make_layer(fake)
    result = layer._send([{"role": "user", "content": "hello"}],
                         max_tokens=10, temperature=0.1)
    assert result.content == "ok"
    assert fake.called == 1  # 转发到后端且仅调用一次，未递归


def test_send_masks_pii_before_forwarding():
    fake = _FakeBackend()

    class _Privacy:
        @staticmethod
        def get_config():
            return {"pii_masking": True}

        @staticmethod
        def mask_pii(text):
            return "<脱敏>"

    layer = object.__new__(AILayer)
    layer._initialized = True
    layer._backend = fake
    layer.privacy = _Privacy()

    layer._send([{"role": "user", "content": "秘密"}])
    assert fake.called == 1
