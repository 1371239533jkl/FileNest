"""
全局数据缓存服务 - 预加载和缓存分类数据，实现零延迟切换
"""
import time
from typing import Optional, Dict, List, Tuple
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from database.db_manager import db
from database.models import FileDAO, ClassificationDAO
from core import FileClassifier
from utils.logger import logger


class DataCacheWorker(QThread):
    """后台预加载工作线程"""
    preload_finished = pyqtSignal(dict, dict)  # tree_data, all_files_cache
    preload_error = pyqtSignal(str)
    
    def __init__(self, file_dao, cls_dao, classifier, parent=None):
        super().__init__(parent)
        self.file_dao = file_dao
        self.cls_dao = cls_dao
        self.classifier = classifier
    
    def run(self):
        try:
            # 预加载分类树
            tree_data = self.classifier.get_classification_tree()
            
            # 预加载"全部文件"的前 100 条
            all_files = self.file_dao.get_all_active_paginated(page=0, page_size=100)
            all_count = self.file_dao.count_active()
            
            # 预加载每个分类的前 50 条（只预加载文件数 > 10 的热门分类）
            hot_categories = {}
            for category, items in tree_data.items():
                type_map = {'按类型': 'by_type', '按日期': 'by_date', '按关键词': 'by_keyword'}
                db_type = type_map.get(category, category)
                for value, count in items:
                    if count >= 10:  # 只预加载文件数 >= 10 的分类
                        try:
                            files = self.file_dao.get_classification_paginated(
                                db_type, value, page=0, page_size=50)
                            hot_categories[f"{db_type}_{value}"] = (files, count)
                        except Exception as e:
                            logger.debug(f"预加载分类失败 {category}/{value}: {e}")
            
            logger.info(f"预加载完成: 分类树 {len(tree_data)} 维, "
                       f"全部文件 {all_count} 条, "
                       f"热门分类 {len(hot_categories)} 个")
            
            self.preload_finished.emit(tree_data, {
                'all_files': (all_files, all_count),
                'hot_categories': hot_categories
            })
        except Exception as e:
            self.preload_error.emit(str(e))


class GlobalDataCache(QObject):
    """全局数据缓存服务（单例）"""
    _instance: Optional['GlobalDataCache'] = None
    
    def __init__(self):
        super().__init__()
        self.file_dao = FileDAO(db)
        self.cls_dao = ClassificationDAO(db)
        self.classifier = FileClassifier()
        
        # 缓存数据
        self._tree_cache: Optional[dict] = None
        self._tree_cache_time: float = 0
        
        # 文件列表缓存：{mode_key: (files, total_count, timestamp)}
        self._files_cache: Dict[str, Tuple[list, int, float]] = {}
        self._cache_max_age = 60  # 缓存有效期（秒）
        
        # 预加载工作线程
        self._preload_worker: Optional[DataCacheWorker] = None
        self._is_preloaded = False
    
    @classmethod
    def get_instance(cls) -> 'GlobalDataCache':
        if cls._instance is None:
            cls._instance = GlobalDataCache()
        return cls._instance
    
    def start_preload(self):
        """启动后台预加载（在应用启动时调用）"""
        if self._is_preloaded or self._preload_worker is not None:
            return
        
        logger.info("开始预加载分类数据...")
        self._preload_worker = DataCacheWorker(
            self.file_dao, self.cls_dao, self.classifier, self)
        self._preload_worker.preload_finished.connect(self._on_preload_finished)
        self._preload_worker.preload_error.connect(self._on_preload_error)
        self._preload_worker.start()
    
    def _on_preload_finished(self, tree_data: dict, files_cache: dict):
        """预加载完成的回调"""
        self._tree_cache = tree_data
        self._tree_cache_time = time.time()
        
        # 填充文件列表缓存
        all_files, all_count = files_cache['all_files']
        self._files_cache['all_page_0'] = (all_files, all_count, time.time())
        
        for key, (files, count) in files_cache['hot_categories'].items():
            self._files_cache[f"{key}_page_0"] = (files, count, time.time())
        
        self._is_preloaded = True
        self._preload_worker = None
        logger.info("分类数据预加载完成，已缓存到内存")
    
    def _on_preload_error(self, error_msg: str):
        """预加载失败的回调"""
        logger.error(f"预加载失败: {error_msg}")
        self._preload_worker = None
    
    def get_tree_data(self) -> Optional[dict]:
        """获取分类树数据（优先从缓存读取）"""
        if self._tree_cache is not None and (time.time() - self._tree_cache_time) < self._cache_max_age:
            return self._tree_cache
        return None
    
    def get_files(self, mode, page: int, page_size: int) -> Optional[Tuple[list, int]]:
        """获取文件列表（优先从缓存读取）"""
        mode_key = self._get_mode_key(mode, page)
        if mode_key in self._files_cache:
            files, total_count, timestamp = self._files_cache[mode_key]
            if (time.time() - timestamp) < self._cache_max_age:
                return (files, total_count)
        return None
    
    def cache_files(self, mode, page: int, files: list, total_count: int):
        """缓存文件列表"""
        mode_key = self._get_mode_key(mode, page)
        self._files_cache[mode_key] = (files, total_count, time.time())
        
        # 限制缓存大小
        if len(self._files_cache) > 50:
            oldest_key = min(self._files_cache.keys(), 
                           key=lambda k: self._files_cache[k][2])
            del self._files_cache[oldest_key]
    
    def invalidate_cache(self):
        """清除缓存（数据变化时调用）"""
        self._tree_cache = None
        self._tree_cache_time = 0
        self._files_cache.clear()
        self._is_preloaded = False
        logger.debug("全局数据缓存已清除")
    
    def _get_mode_key(self, mode, page: int) -> str:
        """生成缓存键"""
        if mode == 'all':
            return f"all_page_{page}"
        else:
            _, cls_type, cls_value = mode
            return f"{cls_type}_{cls_value}_page_{page}"
