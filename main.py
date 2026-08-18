"""
智能文件管家 - 应用入口
ponytail: 移除 MySQL 密码检查，使用 SQLite 零配置。
"""
import sys
import os

# 确保项目根目录在路径中
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import Qt, QTimer

from ui.main_window import MainWindow
from utils.logger import logger
from utils.display_utils import get_platform_font
from core.data_cache import GlobalDataCache


def _install_excepthook():
    """全局未捕获异常处理：写入日志并弹窗提示，避免崩溃无声无息。

    这是小版本迭代"发现问题"的基础——任何未捕获异常都会留下
    traceback 证据（logs/app.log），用户反馈时能快速定位。
    """
    import traceback

    def _hook(exc_type, exc_value, exc_tb):
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logger.error(f"未捕获异常:\n{text}")
        try:
            QMessageBox.critical(
                None, "程序发生错误",
                f"遇到未预期的错误，详情已写入日志。\n\n"
                f"{exc_type.__name__}: {exc_value}\n\n"
                f"可打开 logs/app.log 查看完整堆栈，或反馈此信息。")
        except Exception:
            pass  # 弹窗失败时日志已记录，不阻塞退出

    sys.excepthook = _hook


def main():
    logger.info("启动智能文件管家...")
    _install_excepthook()

    # 启用高 DPI 适配（Windows 125%/150%/200% 缩放下字体和图片清晰度关键）
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # 设置全局字体（跨平台兼容）
    app.setFont(get_platform_font(10))

    window = MainWindow()
    window.show()

    # 延迟预加载：UI 先渲染，空闲后再启动后台数据加载
    QTimer.singleShot(100, lambda: GlobalDataCache.get_instance().start_preload())

    logger.info("应用启动完成")
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
