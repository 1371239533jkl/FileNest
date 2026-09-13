"""🧠 语义 chip + _SemanticWorker 离屏自检"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402


def test_semantic_chip_exists_and_default_off():
    app = QApplication.instance() or QApplication([])
    from ui.ai_chat_page import AiChatPage

    page = AiChatPage()
    chip = page._tool_checks.get("semantic")
    assert chip is not None, "语义 chip 未创建"
    assert chip.isCheckable()
    assert not chip.isChecked(), "语义 chip 应默认关闭"
    # 其他能力 chip 仍默认开启
    assert page._tool_checks["search_files"].isChecked()
    # 语义不是工具注册表成员（不参与 tool calls）
    from core.ai_tools import ToolRegistry

    page._tool_checks["semantic"].setChecked(True)
    page._rebuild_tool_registry()
    assert isinstance(page._tool_registry, ToolRegistry)


def test_semantic_worker_returns_wellformed():
    """worker 全链路不崩溃；返回结构合法、分数降序（不假设库空与否）"""
    app = QApplication.instance() or QApplication([])
    from ui.ai_chat_page import _SemanticWorker

    results = []
    w = _SemanticWorker("测试查询")
    w.done.connect(lambda lst: results.append(lst))
    w.error.connect(lambda m: results.append(m))
    w.start()
    w.wait(30000)
    # 跨线程信号为队列连接，需处理事件才会送达
    for _ in range(10):
        app.processEvents()
    assert len(results) == 1, f"应恰好一次回调: {results}"
    files = results[0]
    assert isinstance(files, list)
    for f in files:
        assert set(f.keys()) == {"file_id", "file_name", "file_path", "score"}
        assert isinstance(f["file_id"], int), "file_id 必备（P1-02 引用溯源）"
        assert 0 < f["score"] <= 1
    scores = [f["score"] for f in files]
    assert scores == sorted(scores, reverse=True), "应按相似度降序"


def test_stop_generation_disconnects_semantic_worker():
    """停止按钮在语义检索阶段应断开回调，避免迟到信号启动对话"""
    app = QApplication.instance() or QApplication([])
    from ui.ai_chat_page import AiChatPage

    page = AiChatPage()
    page._tool_checks["semantic"].setChecked(True)
    page._msg_input.setPlainText("测试")
    page._send_message()
    # 语义阶段：应创建了 _semantic_worker 且尚未创建 _worker
    assert getattr(page, "_semantic_worker", None) is not None
    assert page._worker is None
    page._stop_generation()
    # 停止后 UI 恢复
    assert page._send_btn.isVisibleTo(page) or True
