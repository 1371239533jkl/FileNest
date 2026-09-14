"""
命令行接口（批次6-4）。

轻量 CLI：搜索 / 扫描 / 标签，JSON 输出便于脚本集成。
写操作（标签添加/删除）继承 FileManager 的安全校验与审计（写操作历史）。

用法：
    python cli.py search --name "报告" --type document --limit 20
    python cli.py scan /path/to/dir --recursive
    python cli.py tag add --file-id 123 --tag "重要"
    python cli.py tag list --file-id 123
    python cli.py tag list-all
"""
import argparse
import json
import sys
import os

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.db_manager import db
from database.models import FileDAO, TagDAO
from core.tag_manager import TagManager
from utils.display_utils import format_size


def _out(data, pretty: bool = False):
    """输出 JSON。"""
    indent = 2 if pretty else None
    print(json.dumps(data, ensure_ascii=False, default=str, indent=indent))


def cmd_search(args):
    dao = FileDAO(db)
    results = dao.search(
        name=args.name,
        file_type=args.type,
        extension=args.ext,
        min_size=args.min_size,
        max_size=args.max_size,
    )
    # 截断为关键字段
    items = []
    for r in (results or [])[:args.limit]:
        items.append({
            'id': r['id'],
            'file_name': r['file_name'],
            'file_path': r['file_path'],
            'file_size': r['file_size'],
            'file_type': r.get('file_type', ''),
            'modify_time': r.get('modify_time', ''),
        })
    _out({
        'command': 'search',
        'total': len(items),
        'items': items,
    }, pretty=args.pretty)


def cmd_scan(args):
    """扫描目录并索引（轻量：直接调用 file_scanner + file_dao）。"""
    from core.file_scanner import get_file_info
    import os
    dao = FileDAO(db)

    directory = args.directory
    if not os.path.isdir(directory):
        _out({'error': f'目录不存在: {directory}'})
        sys.exit(1)

    count = 0
    skipped = 0
    errors = []

    if args.recursive:
        for root, _dirs, files in os.walk(directory):
            for fn in files:
                full = os.path.join(root, fn)
                try:
                    info = get_file_info(full)
                    dao.insert(info)
                    count += 1
                except Exception as e:  # noqa: BLE001
                    skipped += 1
                    errors.append(f'{full}: {e}')
    else:
        for fn in os.listdir(directory):
            full = os.path.join(directory, fn)
            if os.path.isfile(full):
                try:
                    info = get_file_info(full)
                    dao.insert(info)
                    count += 1
                except Exception as e:  # noqa: BLE001
                    skipped += 1
                    errors.append(f'{full}: {e}')

    _out({
        'command': 'scan',
        'directory': directory,
        'indexed': count,
        'skipped': skipped,
        'errors': errors[:10],
    }, pretty=args.pretty)


def cmd_tag_add(args):
    mgr = TagManager()
    if args.file_id:
        ok = mgr.add_tag(args.file_id, args.tag)
        _out({
            'command': 'tag.add',
            'file_id': args.file_id,
            'tag': args.tag,
            'success': ok,
        }, pretty=args.pretty)
    elif args.path:
        dao = FileDAO(db)
        rec = dao.get_by_path(args.path)
        if not rec:
            _out({'error': f'文件未索引: {args.path}'})
            sys.exit(1)
        ok = mgr.add_tag(rec['id'], args.tag)
        _out({
            'command': 'tag.add',
            'file_id': rec['id'],
            'path': args.path,
            'tag': args.tag,
            'success': ok,
        }, pretty=args.pretty)


def cmd_tag_remove(args):
    mgr = TagManager()
    if args.file_id:
        ok = mgr.remove_tag(args.file_id, args.tag)
    elif args.path:
        dao = FileDAO(db)
        rec = dao.get_by_path(args.path)
        if not rec:
            _out({'error': f'文件未索引: {args.path}'})
            sys.exit(1)
        ok = mgr.remove_tag(rec['id'], args.tag)
        args.file_id = rec['id']
    _out({
        'command': 'tag.remove',
        'file_id': args.file_id,
        'tag': args.tag,
        'success': ok,
    }, pretty=args.pretty)


def cmd_tag_list(args):
    dao = TagDAO(db)
    if args.file_id:
        tags = dao.get_tags_by_file(args.file_id)
        _out({
            'command': 'tag.list',
            'file_id': args.file_id,
            'tags': [t['tag_name'] for t in (tags or [])],
        }, pretty=args.pretty)
    else:
        all_tags = dao.get_all_tags()
        _out({
            'command': 'tag.list-all',
            'total': len(all_tags),
            'tags': [t['tag_name'] for t in (all_tags or [])],
        }, pretty=args.pretty)


def main():
    parser = argparse.ArgumentParser(
        prog='smart-file-manager',
        description='Smart File Manager CLI')
    parser.add_argument('--pretty', action='store_true', help='美化 JSON 输出')
    parser.add_argument('--db', help='指定数据库路径（默认使用 config.py 配置）')
    sub = parser.add_subparsers(dest='cmd', required=True)

    # search
    p_search = sub.add_parser('search', help='搜索文件')
    p_search.add_argument('--name', help='文件名关键词（支持全文检索）')
    p_search.add_argument('--type', help='文件类型：document/image/video/audio/archive/code/other')
    p_search.add_argument('--ext', help='扩展名过滤，如 .pdf')
    p_search.add_argument('--min-size', type=int, help='最小大小（字节）')
    p_search.add_argument('--max-size', type=int, help='最大大小（字节）')
    p_search.add_argument('--limit', type=int, default=50, help='结果上限，默认 50')
    p_search.set_defaults(func=cmd_search)

    # scan
    p_scan = sub.add_parser('scan', help='扫描目录并索引')
    p_scan.add_argument('directory', help='要扫描的目录路径')
    p_scan.add_argument('--recursive', '-r', action='store_true', help='递归扫描子目录')
    p_scan.set_defaults(func=cmd_scan)

    # tag
    p_tag = sub.add_parser('tag', help='标签管理')
    tag_sub = p_tag.add_subparsers(dest='tag_cmd', required=True)

    p_tag_add = tag_sub.add_parser('add', help='给文件添加标签')
    p_tag_add.add_argument('--file-id', type=int, help='文件 ID')
    p_tag_add.add_argument('--path', help='文件路径（二选一）')
    p_tag_add.add_argument('--tag', required=True, help='标签名')
    p_tag_add.set_defaults(func=cmd_tag_add)

    p_tag_rm = tag_sub.add_parser('remove', help='移除文件标签')
    p_tag_rm.add_argument('--file-id', type=int, help='文件 ID')
    p_tag_rm.add_argument('--path', help='文件路径（二选一）')
    p_tag_rm.add_argument('--tag', required=True, help='标签名')
    p_tag_rm.set_defaults(func=cmd_tag_remove)

    p_tag_list = tag_sub.add_parser('list', help='列出标签')
    p_tag_list.add_argument('--file-id', type=int, help='指定文件的标签')
    p_tag_list.set_defaults(func=cmd_tag_list)

    args = parser.parse_args()

    # 初始化数据库
    if args.db:
        import config
        config.DB_PATH = args.db
    db.init_database()

    try:
        args.func(args)
    except Exception as e:  # noqa: BLE001
        _out({'error': str(e)}, pretty=args.pretty)
        sys.exit(1)


if __name__ == '__main__':
    main()
