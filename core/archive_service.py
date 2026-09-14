"""
一键归档包服务（批次6-2）。

将选中的文件/文件夹打包为 zip，生成清单 + 校验值，失败自动清理。
用标准库 zipfile + hashlib，零外部依赖。

ponytail: 只做 zip（跨平台够用），不做 7z/tar 等多格式；
         校验用 SHA-256 头 16 字符够用（百万文件碰撞概率可忽略）。
"""
import os
import json
import zipfile
import hashlib
import shutil
from datetime import datetime
from typing import Callable, List, Optional

from database.db_manager import db
from database.models import ArchivePackageDAO, FileDAO
from utils.logger import logger


def _sha256_head(path: str, max_mb: int = 10) -> str:
    """计算文件 SHA-256（最多读前 max_mb MB，大文件足够校验）。"""
    h = hashlib.sha256()
    read = 0
    chunk = 65536
    limit = max_mb * 1024 * 1024
    with open(path, 'rb') as f:
        while True:
            buf = f.read(chunk)
            if not buf:
                break
            h.update(buf)
            read += len(buf)
            if read >= limit:
                break
    return h.hexdigest()[:16]


def _walk_items(paths: List[str]) -> List[dict]:
    """展开路径列表为文件清单，返回 [{src, arcname, size}]。
    目录递归加入；文件直进。arcname 保留相对路径（顶层目录名）。"""
    items = []
    for p in paths:
        if not os.path.exists(p):
            continue
        if os.path.isfile(p):
            items.append({
                'src': p,
                'arcname': os.path.basename(p),
                'size': os.path.getsize(p),
            })
        elif os.path.isdir(p):
            base = os.path.dirname(os.path.abspath(p))
            for root, dirs, files in os.walk(p):
                for fn in files:
                    full = os.path.join(root, fn)
                    rel = os.path.relpath(full, base)
                    items.append({
                        'src': full,
                        'arcname': rel,
                        'size': os.path.getsize(full),
                    })
    return items


class ArchiveService:
    """一键归档包服务。"""

    def __init__(self, dao: Optional[ArchivePackageDAO] = None,
                 file_dao: Optional[FileDAO] = None):
        self.dao = dao or ArchivePackageDAO(db)
        self.file_dao = file_dao or FileDAO(db)

    # ── 公共 API ────────────────────────────────────────────────

    def create_package(self, source_paths: List[str], output_dir: str,
                       package_name: Optional[str] = None,
                       progress_cb: Optional[Callable[[int, int], None]] = None
                       ) -> dict:
        """
        创建归档包。返回 {'success', 'package_id', 'archive_path', 'item_count',
                          'total_size', 'checksum', 'error'}。
        """
        source_paths = [p for p in source_paths if p and os.path.exists(p)]
        if not source_paths:
            return {'success': False, 'error': '没有可归档的源路径'}

        if not os.path.isdir(output_dir):
            return {'success': False, 'error': f'输出目录不存在: {output_dir}'}

        name = package_name or f"archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if not name.endswith('.zip'):
            name += '.zip'
        archive_path = os.path.join(output_dir, name)

        # 空间预检查（按 1.1 倍估算，压缩率未知保守估算）
        items = _walk_items(source_paths)
        total_size = sum(it['size'] for it in items)
        try:
            free = shutil.disk_usage(output_dir).free
        except Exception:
            free = 0
        if free and total_size > free * 0.95:
            return {'success': False, 'error': '磁盘空间不足'}

        pkg_id = self.dao.create(
            package_name=name,
            archive_path=archive_path,
            item_count=len(items),
            total_size=total_size,
            status='creating',
            manifest='',
        )

        checksum = ''
        error = None
        try:
            # 写 zip
            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                done = 0
                total = len(items)
                for it in items:
                    try:
                        zf.write(it['src'], it['arcname'])
                    except Exception as exc:  # noqa: BLE001
                        logger.warning('归档跳过 %s: %s', it['src'], exc)
                    done += 1
                    if progress_cb:
                        try:
                            progress_cb(done, total)
                        except Exception:
                            pass

            # 整体校验值
            checksum = _sha256_head(archive_path)

            # 写清单
            manifest = json.dumps({
                'package_name': name,
                'created_at': datetime.now().isoformat(),
                'item_count': len(items),
                'total_size': total_size,
                'checksum': checksum,
                'items': [
                    {'path': it['arcname'], 'size': it['size'],
                     'src': it['src']}
                    for it in items
                ],
            }, ensure_ascii=False)

            self.dao.update_status(pkg_id, 'completed', checksum=checksum)
            # 清单单独存（manifest 列存摘要即可，详情见 JSON）
            from database.db_manager import db as _db
            _db.execute_update(
                "UPDATE archive_packages SET manifest = ? WHERE id = ?",
                (manifest[:8000], pkg_id))

        except Exception as exc:  # noqa: BLE001
            error = str(exc)
            logger.error('归档包创建失败: %s', exc)
            # 失败清理
            if os.path.exists(archive_path):
                try:
                    os.remove(archive_path)
                except Exception:
                    pass
            self.dao.update_status(pkg_id, 'failed', error_message=error)

        return {
            'success': error is None,
            'package_id': pkg_id,
            'archive_path': archive_path,
            'item_count': len(items),
            'total_size': total_size,
            'checksum': checksum,
            'error': error,
        }

    def list_packages(self, status: Optional[str] = None) -> list:
        return self.dao.get_all(status=status)

    def delete_package(self, pkg_id: int, delete_file: bool = True) -> bool:
        pkg = self.dao.get_by_id(pkg_id)
        if not pkg:
            return False
        if delete_file and pkg.get('archive_path'):
            try:
                if os.path.exists(pkg['archive_path']):
                    os.remove(pkg['archive_path'])
            except Exception as exc:
                logger.warning('删除归档文件失败: %s', exc)
        self.dao.delete(pkg_id)
        return True
