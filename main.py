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
from config import MYSQL_CONFIG

_WEAK_PASSWORDS = {'123456', 'password', 'root', 'admin', '', 'CHANGE_ME_YOUR_MYSQL_PASSWORD'}


def _check_password():
    """检查数据库密码安全性：弱密码警告、非 ASCII 字符报错"""
    pwd = MYSQL_CONFIG.get('password', '')
    if pwd in _WEAK_PASSWORDS:
        logger.warning(
            "【安全警告】数据库密码仍为默认占位符，请在 .env 文件中修改 SMART_FM_DB_PASSWORD！"
        )
    # PyMySQL 认证阶段用 latin-1 编码发送密码，非 ASCII 字符会导致 codec 错误
    try:
        pwd.encode('latin-1')
    except UnicodeEncodeError:
        logger.error(
            "【致命错误】数据库密码包含非 ASCII 字符，PyMySQL 无法处理。\n"
            "请修改 .env 中的 SMART_FM_DB_PASSWORD 为纯英文/数字密码。"
        )
        raise ValueError(
            "数据库密码包含非 ASCII 字符，PyMySQL 认证阶段不支持。"
            "请在 .env 中设置纯英文/数字密码。"
        )


def main():
    _check_password()
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
