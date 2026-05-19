"""
智能文件管家 - 全局配置
"""
import os
from dotenv import load_dotenv

# 加载 .env 文件（如果存在），优先级：环境变量 > .env 文件 > 默认值
load_dotenv()

# 应用信息
APP_NAME = "智能文件管家"
APP_VERSION = "1.0.0"

# 窗口配置
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 800
MIN_WINDOW_WIDTH = 1000
MIN_WINDOW_HEIGHT = 700

# MySQL数据库配置（密码从环境变量读取，不再硬编码）
MYSQL_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': os.getenv('SMART_FM_DB_PASSWORD', '123456'),
    'database': 'smart_file_manager',
    'charset': 'utf8mb4',
    'autocommit': True
}

# 文件类型定义
FILE_TYPES = {
    'image': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', '.ico',
              '.tiff', '.tif', '.heic', '.heif', '.raw', '.cr2', '.nef', '.arw',
              '.dng', '.avif', '.psd', '.ai', '.eps'],
    'document': ['.pdf', '.doc', '.docx', '.txt', '.xls', '.xlsx', '.ppt', '.pptx',
                 '.csv', '.rtf', '.odt', '.md', '.rst'],
    'code': ['.py', '.js', '.ts', '.jsx', '.tsx', '.html', '.htm', '.css', '.scss',
             '.less', '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.xml',
             '.sql', '.java', '.cpp', '.c', '.h', '.hpp', '.php', '.rb', '.go',
             '.rs', '.swift', '.kt', '.sh', '.bat', '.ps1', '.vue', '.svelte'],
    'video': ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v',
              '.rmvb', '.rm', '.ts', '.m2ts', '.mpeg', '.mpg', '.3gp', '.vob', '.ogv'],
    'audio': ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a',
              '.mid', '.midi', '.ape', '.opus', '.aiff'],
    'archive': ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz',
                '.tgz', '.cab', '.dmg', '.iso'],
    'executable': ['.exe', '.msi', '.dll', '.apk', '.deb', '.rpm', '.AppImage'],
    'font': ['.ttf', '.otf', '.woff', '.woff2', '.eot'],
}

# 文件类型中文映射
FILE_TYPE_NAMES = {
    'image': '图片',
    'document': '文档',
    'code': '代码',
    'video': '视频',
    'audio': '音频',
    'archive': '压缩包',
    'executable': '可执行文件',
    'font': '字体',
    'other': '其他',
}

# 重命名模板
DEFAULT_RENAME_PATTERN = "{date}_{type}_{original_name}"

# 扫描配置
DEFAULT_RECURSIVE = True
INCLUDE_HIDDEN_FILES = False
HASH_ALGORITHM = 'sha256'
HASH_BLOCK_SIZE = 65536  # 64KB 分块读取
MAX_FILE_SIZE_FOR_HASH = 500 * 1024 * 1024  # 500MB

# 去重策略
DEDUP_STRATEGIES = {
    'keep_newest': '保留最新文件',
    'keep_oldest': '保留最旧文件',
    'keep_shortest_path': '保留路径最短',
    'manual': '手动选择',
}
DEFAULT_DEDUP_STRATEGY = 'keep_newest'

# 日志配置
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'app.log')
LOG_LEVEL = 'INFO'
LOG_MAX_SIZE = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5

# 默认分类关键词规则
DEFAULT_KEYWORD_RULES = {
    '工作': ['报告', '会议', '方案', '合同', '发票', 'report', 'meeting', 'invoice'],
    '学习': ['笔记', '课件', '作业', '论文', 'note', 'homework', 'thesis'],
    '生活': ['照片', '旅游', '美食', 'photo', 'travel', 'food'],
    '项目': ['代码', '设计', '需求', '测试', 'code', 'design', 'test'],
}
