"""
通用后台批量分类线程 - 供扫描后处理和手动重新分类共用
独立 DB 连接，不抢主线程的连接；批量 flush 提高性能。
"""
import pymysql
from pymysql.cursors import DictCursor
from datetime import datetime

from PyQt6.QtCore import QThread, pyqtSignal

from config import MYSQL_CONFIG
from utils.logger import logger


class BatchClassifyWorker(QThread):
    """后台批量分类工作线程

    参数:
        classifier:   FileClassifier 实例（用于 _classify_file_in_memory）
        do_metadata:  扫描完成后顺带提取元数据
        parent:       QObject 父级
    """
    progress = pyqtSignal(int, int)   # current, total
    finished = pyqtSignal(int)        # classified_count
    error = pyqtSignal(str)

    def __init__(self, classifier=None, do_metadata: bool = False, parent=None):
        super().__init__(parent)
        self.classifier = classifier
        self.do_metadata = do_metadata
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        conn = pymysql.connect(**MYSQL_CONFIG)
        try:
            with conn.cursor(DictCursor) as cur:
                cur.execute(
                    "SELECT * FROM files WHERE status = 'active' "
                    "ORDER BY scan_time DESC")
                files = cur.fetchall()

            total = len(files)
            classified = 0
            batch = []

            for i, record in enumerate(files):
                if self._cancelled:
                    break

                file_id = record['id']
                try:
                    # ── 元数据提取（可选）──
                    if self.do_metadata:
                        self._extract_and_save_metadata(conn, record)

                    # ── 分类 ──
                    if self.classifier is not None:
                        with conn.cursor() as cur:
                            cur.execute(
                                "DELETE FROM file_classifications WHERE file_id = %s",
                                (file_id,))

                        cls_results = self.classifier._classify_file_in_memory(record)
                        if cls_results:
                            classified += 1

                        now = datetime.now()
                        for cls_type, cls_value, confidence in cls_results:
                            batch.append((file_id, cls_type, cls_value, now, confidence))

                    # 每 100 条 flush
                    if len(batch) >= 100:
                        self._flush_batch(conn, batch)
                        batch.clear()

                except Exception as e:
                    logger.warning(
                        f"批量分类: 处理文件 {record.get('file_name', '?')} 失败: {e}")

                # 进度上报（每 50 条）
                if i % 50 == 0:
                    self.progress.emit(i + 1, total)

            # 最后一次 flush
            if batch:
                self._flush_batch(conn, batch)

            self.progress.emit(total, total)
            logger.info(f"批量分类完成: {classified}/{total}")
            self.finished.emit(classified)

        except Exception as e:
            logger.error(f"批量分类出错: {e}")
            self.error.emit(str(e))
        finally:
            conn.close()

    # ── 私有方法 ──

    @staticmethod
    def _flush_batch(conn, batch: list) -> None:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO file_classifications "
                "(file_id, classification_type, classification_value, "
                "classification_time, confidence_score) "
                "VALUES (%s, %s, %s, %s, %s)", batch)
            conn.commit()

    @staticmethod
    def _extract_and_save_metadata(conn, record: dict) -> None:
        """提取并保存文件元数据（异常只记录日志，不中断流程）"""
        try:
            from core.metadata_extractor import extract_metadata
            metadata = extract_metadata(record['file_path'], record['file_type'])
            if not metadata:
                return

            cols = ['file_id'] + list(metadata.keys())
            placeholders = ', '.join(['%s'] * len(cols))
            update_parts = ', '.join(f'`{k}`=VALUES(`{k}`)' for k in metadata)
            sql = (f"INSERT INTO file_metadata (`{'`, `'.join(cols)}`) "
                   f"VALUES ({placeholders}) "
                   f"ON DUPLICATE KEY UPDATE {update_parts}")
            with conn.cursor() as cur:
                cur.execute(sql, (record['id'],) + tuple(metadata.values()))
        except Exception as e:
            logger.warning(
                f"元数据提取失败 {record.get('file_name', '?')}: {e}")
