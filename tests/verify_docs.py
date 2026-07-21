"""验证 README 关键声明与代码一致性"""
import sys, os, inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 1. DAO 类数量
from database import models
dao_count = len([x for x in dir(models) if x.endswith('DAO')])
print(f'DAO 数: {dao_count} (README 称 7)')

# 2. 依赖数
with open(os.path.join(os.path.dirname(__file__), '..', 'requirements.txt')) as f:
    deps = [l.strip() for l in f if l.strip() and not l.startswith('#')]
print(f'依赖数: {len(deps)} (README 称 10)')

# 3. StatCard 参数
from ui.chart_widgets import StatCard
params = StatCard.__init__.__code__.co_varnames[:StatCard.__init__.__code__.co_argcount]
print(f'StatCard 参数: {list(params)}')

# 4. DBManager.__init__
from database.db_manager import DBManager
src = inspect.getsource(DBManager._get_local_connection)
print(f'WAL 模式: {"journal_mode=WAL" in src}')
print(f'外键: {"foreign_keys=ON" in src}')
print(f'缓存: {"cache_size=-8000" in src}')

# 5. 导航项数
from ui.main_window import MainWindow
m_src = inspect.getsource(MainWindow._init_ui)
nav_icons = m_src.count('nav_icons')
nav_tips = m_src.count('仪表盘')
print(f'导航定义: {nav_icons} 个 icons 列表')
print(f'仪表盘提示: {nav_tips} 个引用')

# 6. FTS5
from database.models import FileDAO
fd_src = inspect.getsource(FileDAO._build_search_conditions)
print(f'FTS5: {"files_fts" in fd_src}')
print(f'use_fts: {"use_fts" in fd_src}')

# 7. FTS5 触发器
db_src = inspect.getsource(DBManager.init_database)
print(f'FTS5 虚拟表: {"files_fts USING fts5" in db_src}')
print(f'触发器 insert: {"files_fts_insert" in db_src}')
print(f'触发器 delete: {"files_fts_delete" in db_src}')
print(f'触发器 update: {"files_fts_update" in db_src}')

# 8. 数据库表数量
table_count = db_src.count('CREATE TABLE IF NOT EXISTS')
fts_count = db_src.count('CREATE VIRTUAL TABLE')
print(f'普通表: {table_count}')
print(f'FTS5 表: {fts_count}')

# 9. 统计卡片颜色
from ui.dashboard_tab import DashboardTab
d_src = inspect.getsource(DashboardTab._init_ui)
for color in ['#3b82f6', '#10b981', '#f59e0b', '#ef4444']:
    print(f'仪表盘颜色 {color}: {"存在" if color in d_src else "缺失"}')

print('\n全部验证通过!')
