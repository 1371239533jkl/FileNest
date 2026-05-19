"""
智能文件管家 - 应用入口
"""
import sys
import os

# 确保项目根目录在路径中
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from ui.main_window import MainWindow
from utils.logger import logger


def main():
    logger.info("启动智能文件管家...")

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # 设置全局字体
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    window = MainWindow()
    window.show()

    logger.info("应用启动完成")
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
