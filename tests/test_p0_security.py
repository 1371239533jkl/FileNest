"""P0 安全修复回归测试。

覆盖：
- P0-6 出站消息在 backend 层统一脱敏（含工具循环路径）
- P0-5 AI 禁止目录过滤真正生效
- P0-3 永久删除核心层强制确认
- P0-4 归档包名路径穿越防护
- P0-2 对外监听强制 API Key
"""

import pytest


# ── P0-6 后端统一脱敏 ─────────────────────────────────────────

def test_backend_sanitizes_outgoing_messages():
    from core.ai_backends import OpenAICompatibleBackend

    backend = OpenAICompatibleBackend(
        api_key="x", base_url="http://localhost", model="m",
        sanitize=lambda t: t.replace("SECRET", "<隐藏>"))

    original = [{"role": "user", "content": "token=SECRET"}]
    prepared = backend._prepare_messages(original)

    assert prepared[0]["content"] == "token=<隐藏>"
    # 不修改调用方原始列表
    assert original[0]["content"] == "token=SECRET"


def test_backend_without_sanitize_passes_through():
    from core.ai_backends import OpenAICompatibleBackend

    backend = OpenAICompatibleBackend(
        api_key="x", base_url="http://localhost", model="m")
    msgs = [{"role": "user", "content": "原文"}]
    assert backend._prepare_messages(msgs) is msgs


# ── P0-5 AI 禁止目录 ──────────────────────────────────────────

def test_is_forbidden_ai_path_uses_privacy(monkeypatch):
    import core.ai_tools as tools

    class _StubPrivacy:
        def is_path_forbidden(self, path):
            return path.startswith("/secret")

    # _is_forbidden_ai_path 内部 `from core.ai_privacy import AIPrivacy`，
    # 打桩模块属性即可，避免实例化真实 AIPrivacy（会连库）
    monkeypatch.setattr("core.ai_privacy.AIPrivacy", _StubPrivacy)

    assert tools._is_forbidden_ai_path("/secret/report.docx") is True
    assert tools._is_forbidden_ai_path("/public/report.docx") is False
    assert tools._is_forbidden_ai_path("") is False


def test_ai_layer_filters_forbidden_files():
    from core.ai_layer import AILayer

    class _StubPrivacy:
        def filter_forbidden_files(self, files):
            return ([f for f in files if not f["forbidden"]],
                    [f for f in files if f["forbidden"]])

    layer = AILayer.__new__(AILayer)  # 绕过 __init__（避免后端网络探测）
    layer.privacy = _StubPrivacy()
    files = [{"file_path": "a", "forbidden": False},
             {"file_path": "b", "forbidden": True}]
    kept = layer._filter_forbidden_files(files)
    assert [f["file_path"] for f in kept] == ["a"]


# ── P0-3 永久删除确认 ─────────────────────────────────────────

def test_permanent_delete_requires_confirm():
    from core.file_manager import FileManager

    fm = FileManager()
    with pytest.raises(PermissionError):
        fm.permanent_delete(1)
    with pytest.raises(PermissionError):
        fm.purge_file(1)


# ── P0-4 归档包名路径穿越 ─────────────────────────────────────

def test_archive_rejects_path_traversal(tmp_path, monkeypatch):
    from core.archive_service import ArchiveService

    src = tmp_path / "a.txt"
    src.write_text("x")
    out = tmp_path / "out"
    out.mkdir()

    # 模拟 basename 净化失效，验证 realpath 归属校验兜底（真正拦截穿越）
    monkeypatch.setattr("core.archive_service.os.path.basename", lambda p: p)
    svc = ArchiveService(dao=object())  # 守卫在触达 dao 之前返回
    res = svc.create_package([str(src)], str(out), package_name="../evil")

    assert res["success"] is False
    assert not (tmp_path / "evil.zip").exists()


# ── P0-2 对外监听强制鉴权 ─────────────────────────────────────

def test_external_host_requires_api_key(monkeypatch):
    pytest.importorskip("fastapi")
    import server

    monkeypatch.setattr(server, "API_KEY", "")
    with pytest.raises(RuntimeError):
        server._require_api_key_for_external_host("0.0.0.0")
    # 回环放行
    server._require_api_key_for_external_host("127.0.0.1")

    # 已设置 Key 则对外放行
    monkeypatch.setattr(server, "API_KEY", "k")
    server._require_api_key_for_external_host("0.0.0.0")
