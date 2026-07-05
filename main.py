"""
智能文件管家 - 应用入口
ponytail: 移除 MySQL 密码检查，使用 SQLite 零配置。
"""
import sys
import os

# 确保项目根目录在路径中
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QTimer

from ui.main_window import MainWindow
from utils.logger import logger
from utils.display_utils import get_platform_font
from core.data_cache import GlobalDataCache


def main():
    logger.info("启动智能文件管家...")

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
