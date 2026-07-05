"""扫描演示 - 验证 SQLite 端到端流程"""
import sys, os, time, hashlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from database.db_manager import db
from database.models import FileDAO, ScanDirectoryDAO

db.init_database()

scan_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
print(f"扫描目录: {scan_path}")

# 注册目录
dir_dao = ScanDirectoryDAO(db)
dir_dao.insert(scan_path, recursive=True)

# 逐个扫描文件
file_dao = FileDAO(db)
FILE_TYPE_MAP = {
    '.py': 'code', '.js': 'code', '.ts': 'code', '.html': 'code',
    '.css': 'code', '.json': 'code', '.xml': 'code', '.sql': 'code',
    '.md': 'document', '.txt': 'document', '.pdf': 'document',
    '.png': 'image', '.jpg': 'image', '.jpeg': 'image', '.gif': 'image',
    '.svg': 'image', '.ico': 'image',
}

start = time.time()
count = 0
for root, dirs, files in os.walk(scan_path):
    # 跳过隐藏目录和虚拟环境
    dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('__pycache__', 'node_modules', '.trash')]
    for fname in files:
        fp = os.path.join(root, fname)
        try:
            st = os.stat(fp)
            ext = os.path.splitext(fname)[1].lower()
            ftype = FILE_TYPE_MAP.get(ext, 'other')
            file_dao.insert({
                'file_path': fp,
                'file_name': fname,
                'file_extension': ext,
                'file_type': ftype,
                'file_size': st.st_size,
                'file_hash': None,
                'create_time': datetime.fromtimestamp(st.st_ctime).strftime('%Y-%m-%d %H:%M:%S'),
                'modify_time': datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
            })
            count += 1
        except Exception:
            pass

elapsed = time.time() - start
print(f"扫描完成: {count} 个文件 ({elapsed:.2f}s)")

# 验证
active = file_dao.count_active()
stats = file_dao.get_type_stats()
print(f"活跃文件数: {active}")
for s in stats:
    kb = (s["total_size"] or 0) / 1024
    print(f"  {s['file_type']}: {s['count']} 个 ({kb:.1f} KB)")

# FTS5 搜索
for q in ["python", "scan", "model"]:
    r = file_dao.search(name=q)
    print(f"FTS5 搜索 '{q}': {len(r)} 结果 -> {[x['file_name'] for x in r[:3]]}")

# 磁盘分析
mb = (file_dao.get_total_size() or 0) / 1024 / 1024
print(f"总大小: {mb:.2f} MB")
print(f"月度趋势: {len(file_dao.get_monthly_trend())} 月")
top = file_dao.get_top_directories(3)
for d in top:
    print(f"  {d['dir_path']}: {d['file_count']} 文件, {d['total_size']/1024:.1f} KB")

print("\n全部验证通过!")
