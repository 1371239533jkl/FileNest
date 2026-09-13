"""批次 5 内容理解自检 —— 感知哈希/版本关系/目录画像/标签层级/OCR 降级。

沿用项目测试惯例：tmp_path 内存式临时库，不依赖真实文件系统规模。
"""
import os
import time

import pytest

from database.db_manager import DBManager
from database.models import FileDAO, TagDAO, VersionRelationDAO


@pytest.fixture()
def temp_db(tmp_path):
    mgr = DBManager()
    mgr.db_path = str(tmp_path / 'test.db')
    mgr.init_database()
    return mgr


@pytest.fixture()
def file_dao(temp_db):
    return FileDAO(temp_db)


def _insert(file_dao, tmp_path, name, content='x', file_type='document',
            mtime=None, sub=None):
    """写文件并入库。sub=子目录名；mtime=相对现在的秒偏移（负数=更早）。"""
    from datetime import datetime
    d = os.path.join(str(tmp_path), sub) if sub else str(tmp_path)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, name)
    if content is not None:  # content=None 保留已有文件内容（如预生成的图片）
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
    if mtime is not None:
        os.utime(path, (time.time() + mtime, time.time() + mtime))
    st = os.stat(path)
    info = {
        'file_path': path, 'file_name': name, 'original_name': None,
        'file_extension': os.path.splitext(name)[1], 'file_type': file_type,
        'file_size': st.st_size, 'file_hash': None,
        'create_time': datetime.fromtimestamp(st.st_ctime).strftime('%Y-%m-%d %H:%M:%S'),
        'modify_time': datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
    }
    file_id = file_dao.insert(info)
    return file_dao.get_by_id(file_id)


# ── 5-1 OCR ──

def test_image_skipped_without_ocr(temp_db):
    """pytesseract 不可用时图片视为不支持（自动降级，不阻断索引）"""
    from core import file_reader
    assert file_reader.can_read_content('doc.txt')
    if not file_reader.ocr_available():
        assert not file_reader.can_read_content('pic.png')
        assert file_reader.read_file_content('pic.png') is None


def test_ocr_extract_with_stub(tmp_path, monkeypatch):
    """stub pytesseract：验证提取文本 + 语言/置信度记录"""
    from types import SimpleNamespace
    from core import file_reader

    fake = SimpleNamespace(
        get_tesseract_version=lambda: '5.0',
        Output=SimpleNamespace(DICT='dict'),
        image_to_data=lambda img, lang=None, output_type=None: {
            'text': ['合同', '最终版'],
            'conf': [92, 80],
        })
    monkeypatch.setitem(__import__('sys').modules, 'pytesseract', fake)
    file_reader._ocr_ok = True
    try:
        monkeypatch.setattr(file_reader, 'ocr_available', lambda: True)
        png = tmp_path / 'pic.png'
        try:
            from PIL import Image
            Image.new('RGB', (8, 8)).save(png)
        except ImportError:
            pytest.skip('Pillow 未安装')
        out = file_reader.read_file_content(str(png))
        assert out is not None
        assert out.startswith('[OCR lang=') and 'conf=' in out
        assert '合同 最终版' in out
        assert file_reader.can_read_content(str(png))
    finally:
        file_reader._ocr_ok = None


# ── 5-2 感知哈希相似图片 ──

def test_dhash_stable_and_hamming(tmp_path):
    from core.image_similarity import dhash, hamming_distance
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        pytest.skip('Pillow/numpy 未安装')
    # 纯色图 dHash 恒为全 0（无梯度），必须用渐变图才有区分度
    grad = np.tile(np.arange(64, dtype=np.uint8), (64, 1))
    a = tmp_path / 'a.png'
    b = tmp_path / 'b.png'   # 同图缩小再放大 → 梯度方向不变
    c = tmp_path / 'c.png'   # 反相渐变 → 完全不同
    Image.fromarray(grad).save(a)
    small = Image.fromarray(grad).resize((32, 32)).resize((64, 64))
    small.save(b)
    Image.fromarray(255 - grad).save(c)
    ha, hb, hc = dhash(str(a)), dhash(str(b)), dhash(str(c))
    assert ha and hb and hc
    assert hamming_distance(ha, hb) == 0
    assert hamming_distance(ha, hc) > 8
    assert dhash(str(tmp_path / 'none.png')) is None


def test_similarity_grouping(temp_db, file_dao, tmp_path):
    try:
        from PIL import Image
    except ImportError:
        pytest.skip('Pillow 未安装')
    from core.image_similarity import SimilarityManager
    import numpy as np
    # 纯色图 dHash 恒为全 0（无梯度），必须用渐变图
    grad = np.tile(np.arange(64, dtype=np.uint8), (64, 1)).astype(np.uint8)
    Image.fromarray(grad).save(tmp_path / 'a.png')
    Image.fromarray(grad).save(tmp_path / 'b.png')
    Image.fromarray(255 - grad).save(tmp_path / 'c.png')
    _insert(file_dao, tmp_path, 'a.png', content=None, file_type='image')
    _insert(file_dao, tmp_path, 'b.png', content=None, file_type='image')
    _insert(file_dao, tmp_path, 'c.png', content=None, file_type='image')
    _insert(file_dao, tmp_path, 'd.txt', file_type='document')
    # 模拟字节级去重已运行：a/b 哈希一致，c 不同
    temp_db.execute_update(
        "UPDATE files SET file_hash='h1' WHERE file_name IN ('a.png','b.png')")
    temp_db.execute_update("UPDATE files SET file_hash='h2' WHERE file_name='c.png'")
    mgr = SimilarityManager(temp_db)
    r = mgr.compute_hashes()
    assert r['computed'] == 3
    groups = mgr.get_groups(threshold=8)
    assert len(groups) == 1
    assert groups[0]['label'] == '完全重复'  # a/b 字节相同
    assert {f['file_name'] for f in groups[0]['files']} == {'a.png', 'b.png'}
    # 哈希增量续算：第二次跑全部跳过
    assert mgr.compute_hashes()['computed'] == 0


# ── 5-3 版本关系 ──

def test_version_detection_and_confirm(temp_db, file_dao, tmp_path):
    from core.version_relations import detect_version_candidates
    now = 0
    for name in ['报告.docx', '报告 副本.docx', '报告final.docx', '无关.txt']:
        _insert(file_dao, tmp_path, name, mtime=now)
        now -= 60
    added = detect_version_candidates(temp_db)
    assert added >= 2  # 报告族按时间相邻 + 族首尾

    dao = VersionRelationDAO(temp_db)
    pending = dao.get_by_status('pending')
    assert pending
    rid = pending[0]['id']
    assert dao.set_status(rid, 'confirmed') == 1
    assert len(dao.get_by_status('pending')) == len(pending) - 1
    confirmed = dao.get_by_status('confirmed')
    assert len(confirmed) == 1
    assert confirmed[0]['name_a'] or confirmed[0]['name_b']
    # 幂等：重复扫描不再新增
    assert detect_version_candidates(temp_db) == 0
    # 解除
    dao.set_status(rid, 'dismissed')
    assert len(dao.get_by_status('dismissed')) == 1


def test_version_family_name_parsing():
    from core.version_relations import _base_name
    assert _base_name('报告(1).docx') == _base_name('报告v2.docx')
    assert _base_name('报告final.docx') == _base_name('报告.docx')
    assert _base_name('合同.docx') != _base_name('报告.docx')


# ── 5-4 目录画像 ──

def test_directory_profile(file_dao, tmp_path):
    _insert(file_dao, tmp_path, 'a.txt', 'xx', sub='docs')
    _insert(file_dao, tmp_path, 'b.pdf', 'xxxx', sub='docs')
    _insert(file_dao, tmp_path, 'c.png', 'x', file_type='image', sub='docs')
    _insert(file_dao, tmp_path, 'outside.txt', 'x')
    p = file_dao.get_directory_profile(os.path.join(str(tmp_path), 'docs'))
    assert p['file_count'] == 3
    assert p['total_size'] == 7
    assert p['type_distribution'][0]['file_type'] == 'document'
    assert p['oldest'] and p['newest']


# ── 5-5 标签层级与别名 ──

def test_tag_hierarchy_and_alias(temp_db):
    dao = TagDAO(temp_db)
    dao.create_tag('工作')
    dao.create_tag('项目A')
    dao.create_tag('项目B')
    assert dao.set_parent('项目A', '工作')
    assert dao.set_parent('项目B', '工作')
    tree = {n['tag_name']: {c['tag_name'] for c in n['children']}
            for n in dao.get_tag_tree()}
    assert tree['工作'] == {'项目A', '项目B'}
    # 防循环：把父设为自己的子 → 拒绝
    assert not dao.set_parent('工作', '项目A')
    assert not dao.set_parent('项目A', '项目A')
    # 层级不被循环尝试破坏
    assert dao.get_tag_tree()[0]['tag_name'] in ('工作', '项目A', '项目B')

    # 别名
    assert dao.add_alias('projA', '项目A')
    assert dao.resolve_alias('projA') == '项目A'
    assert dao.resolve_alias('项目A') == '项目A'
    assert not dao.add_alias('projA', '项目B')  # 唯一约束 → 冲突失败
    assert dao.get_aliases('项目A') == ['projA']

    # 合并时别名随迁（merge_tag 需要 target 存在）
    dao.merge_tag('项目A', '项目B')
    assert dao.resolve_alias('projA') == '项目B'
    assert dao.get_aliases('项目A') == []
    # 颜色
    dao.set_color('项目B', '#89b4fa')
    row = temp_db.execute_one(
        "SELECT color FROM tags WHERE tag_name = '项目B'")
    assert row['color'] == '#89b4fa'


def test_tag_manager_resolves_alias(temp_db, file_dao, tmp_path):
    """TagManager 打标签时把别名归一为规范名"""
    from core.tag_manager import TagManager
    dao = TagDAO(temp_db)
    dao.create_tag('工作')
    dao.add_alias('gongzuo', '工作')
    rec = _insert(file_dao, tmp_path, 'x.txt')
    tm = TagManager(temp_db)
    assert tm.add_tag(rec['id'], 'gongzuo')
    tags = {r['tag_name'] for r in temp_db.execute_query(
        "SELECT tag_name FROM file_tags WHERE file_id = ?", (rec['id'],))}
    assert tags == {'工作'}  # 不是 'gongzuo'


if __name__ == '__main__':
    import subprocess
    raise SystemExit(subprocess.call(['pytest', __file__, '-q']))
