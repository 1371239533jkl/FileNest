"""pytest 全局 fixtures：管理 QApplication 生命周期"""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """为整个测试会话创建唯一的 QApplication，避免退出时崩溃"""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app
    # 显式清理，防止退出时 STATUS_STACK_BUFFER_OVERRUN
    app.processEvents()
