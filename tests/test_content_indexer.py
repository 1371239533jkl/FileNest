"""测试内容索引增量更新：修改指纹跳过、重新索引、单文件失败不阻断。"""
import os
import pytest
from unittest.mock import patch

from database.db_manager import DBManager
from core.content_indexer import ContentIndexer
from core.file_reader import read_file_content


@pytest.fixture()
def temp_db(tmp_path):
    mgr = DBManager()
    mgr.db_path = str(tmp_path / 'test.db')
    mgr.init_database()
    return mgr


@pytest.fixture()
def indexer(temp_db):
    with patch('core.content_indexer.db', temp_db):
        yield ContentIndexer()


def _make_record(tmp_path, name='doc.txt', content='hello world'):
    path = os.path.join(str(tmp_path), name)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    return path


def _db_record(indexer, path):
    """向 files 表插入一条真实记录，返回可索引的 record dict（含真实 id）"""
    file_id = indexer.file_dao.insert({
        'file_path': path, 'file_name': os.path.basename(path),
        'original_name': None, 'file_extension': os.path.splitext(path)[1],
        'file_type': 'document', 'file_size': os.path.getsize(path),
        'file_hash': None, 'create_time': None, 'modify_time': None,
    })
    return {'id': file_id, 'file_path': path, 'content_fingerprint': None}


class TestContentIndexIncremental:
    def test_first_index_success(self, indexer, tmp_path):
        path = _make_record(tmp_path)
        record = _db_record(indexer, path)
        assert indexer.index_file(record) == 'indexed'
        assert indexer.content_dao.count() == 1
        # 指纹应已写入
        assert indexer.file_dao.get_content_fingerprint(record['id'])

    def test_unchanged_fingerprint_skipped(self, indexer, tmp_path):
        path = _make_record(tmp_path)
        record = _db_record(indexer, path)
        assert indexer.index_file(record) == 'indexed'
        # 读取指纹后再次索引：应跳过（不重新提取）
        fp = indexer.file_dao.get_content_fingerprint(record['id'])
        record['content_fingerprint'] = fp
        with patch('core.content_indexer.read_file_content',
                   wraps=read_file_content) as mock:
            status = indexer.index_file(record)
        assert status == 'skipped'
        mock.assert_not_called()

    def test_modified_content_reindexed(self, indexer, tmp_path):
        path = _make_record(tmp_path, content='v1')
        record = _db_record(indexer, path)
        assert indexer.index_file(record) == 'indexed'
        fp1 = indexer.file_dao.get_content_fingerprint(record['id'])
        # 修改内容（内容更长，指纹必然变化）
        with open(path, 'w', encoding='utf-8') as f:
            f.write('v2' * 100)
        record['content_fingerprint'] = fp1
        assert indexer.index_file(record) == 'indexed'
        assert indexer.file_dao.get_content_fingerprint(record['id']) != fp1

    def test_unsupported_format_skipped(self, indexer, tmp_path):
        path = os.path.join(str(tmp_path), 'image.png')
        with open(path, 'wb') as f:
            f.write(b'\x89PNG\r\n\x1a\n' + b'0' * 64)
        record = _db_record(indexer, path)
        assert indexer.index_file(record) == 'skipped'

    def test_single_failure_does_not_break_batch(self, indexer, tmp_path):
        """一个文件提取失败不阻断同批其他文件"""
        good = _make_record(tmp_path, name='a.txt', content='aaa')
        bad = _make_record(tmp_path, name='b.txt', content='bbb')
        records = [
            _db_record(indexer, good),
            _db_record(indexer, bad),
        ]
        with patch('core.content_indexer.read_file_content',
                   side_effect=lambda p, max_chars=20000:
                       None if p == bad else read_file_content(p, max_chars)):
            result = indexer.index_records(records)
        assert result['indexed'] == 1
        assert result['failed'] == 1
        assert indexer.content_dao.count() == 1

    def test_batch_result_keys(self, indexer, tmp_path):
        path = _make_record(tmp_path)
        result = indexer.index_records([_db_record(indexer, path)])
        assert set(result.keys()) == {'indexed', 'skipped', 'failed'}
        assert result['indexed'] == 1
