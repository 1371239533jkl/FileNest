"""P1-02 引用溯源协议自检 —— 来源收集/去重/上限/外部注入/编号对齐。

对应 ai_chat_page 语义来源注入 + search_content 全局编号 + 气泡引用 chip 的协议约定。
"""
from core.ai_tools import ToolDefinition, ToolRegistry


def _dummy_tool(name: str) -> ToolDefinition:
    return ToolDefinition(
        name=name, description="dummy", parameters={}, handler=lambda **kw: "ok"
    )


def test_sources_dedup_and_order():
    """多工具命中同一文件按首次出现去重，顺序保持。"""
    reg = ToolRegistry()
    reg.register(_dummy_tool("search_files"))
    reg.register(_dummy_tool("search_content"))
    reg.get("search_files").sources.append(
        {"file_id": 1, "file_name": "a", "file_path": "/a"})
    reg.get("search_files").sources.append(
        {"file_id": 2, "file_name": "b", "file_path": "/b"})
    reg.get("search_content").sources.append(
        {"file_id": 1, "file_name": "a", "file_path": "/a"})
    got = reg.get_sources()
    assert [s["file_id"] for s in got] == [1, 2]


def test_add_sources_and_clear():
    """外部来源（语义检索）注入后参与汇总，clear_sources 一并清空。"""
    reg = ToolRegistry()
    reg.register(_dummy_tool("search_files"))
    reg.add_sources([{"file_id": 9, "file_name": "s", "file_path": "/s"}])
    assert reg.get_sources()[0]["file_id"] == 9
    reg.clear_sources()
    assert reg.get_sources() == []


def test_sources_cap_30():
    """汇总来源上限 30 条，防止极端回答撑爆引用行。"""
    reg = ToolRegistry()
    reg.register(_dummy_tool("t"))
    for i in range(40):
        reg.get("t").sources.append(
            {"file_id": i, "file_name": str(i), "file_path": f"/{i}"})
    assert len(reg.get_sources()) == 30


def test_numbering_base_alignment():
    """协议核心：search_content 的全局编号 base = len(自身 sources)，
    外部来源先注入时编号必须从外部来源数量之后继续，避免与 [来源 N] 撞号。"""
    reg = ToolRegistry()
    reg.register(_dummy_tool("search_content"))
    reg.add_sources([
        {"file_id": i, "file_name": f"f{i}", "file_path": f"/{i}"}
        for i in range(3)
    ])
    base = len(reg.get("search_content").sources)
    assert base == 3  # 后续 content 命中编号从 [来源 4] 继续


def test_tool_execute_error_isolated():
    """工具异常被捕获为错误文本，不向上抛（引用收集不中断对话）。"""
    boom = ToolDefinition(
        name="boom", description="", parameters={}, handler=lambda **kw: 1 / 0
    )
    result = boom.execute({})
    assert "[工具执行错误]" in result


if __name__ == "__main__":
    for fn in [
        test_sources_dedup_and_order,
        test_add_sources_and_clear,
        test_sources_cap_30,
        test_numbering_base_alignment,
        test_tool_execute_error_isolated,
    ]:
        fn()
        print(f"PASS {fn.__name__}")
