"""
智能分类器 - 按类型/日期/关键词分类
"""
from typing import Optional, List, Tuple

from config import FILE_TYPE_NAMES
from database.db_manager import db
from database.models import ClassificationDAO, ClassificationRuleDAO
from utils.date_utils import parse_datetime_safe
from utils.logger import logger


class FileClassifier:
    """文件智能分类器"""

    def __init__(self):
        self.cls_dao = ClassificationDAO(db)
        self.rule_dao = ClassificationRuleDAO(db)
        self._db_rules_cache: Optional[list] = None  # 缓存数据库规则，避免每个文件都查库

    def classify_file(self, file_record: dict) -> List[Tuple[str, str]]:
        """对单个文件进行全维度分类（直接插入数据库）"""
        results = self._classify_file_in_memory(file_record)
        file_id = file_record['id']
        for cls_type, cls_value, confidence in results:
            self.cls_dao.insert(file_id, cls_type, cls_value, confidence)
        return [(t, v) for t, v, _ in results]

    def _classify_file_in_memory(self, file_record: dict) -> List[Tuple[str, str, float]]:
        """对单个文件分类，返回 [(cls_type, cls_value, confidence), ...] 但不操作数据库"""
        results: List[Tuple[str, str, float]] = []

        # 1. 按文件类型分类
        type_cls = self._classify_by_type(file_record)
        if type_cls:
            results.append(('by_type', type_cls, 1.0))

        # 2. 按日期分类
        date_cls = self._classify_by_date(file_record)
        if date_cls:
            results.append(('by_date', date_cls, 1.0))

        # 3. 按关键词/规则分类
        keyword_cls = self._classify_by_rules(file_record)
        if keyword_cls:
            for category, confidence in keyword_cls:
                results.append(('by_keyword', category, confidence))

        return results

    def classify_files(self, file_records: List[dict]) -> int:
        """批量分类"""
        total = len(file_records)
        classified = 0
        for record in file_records:
            try:
                # 先清除旧分类
                self.cls_dao.delete_by_file_id(record['id'])
                result = self.classify_file(record)
                if result:
                    classified += 1
            except Exception as e:
                logger.warning(f"分类文件失败 {record.get('file_name')}: {e}")
        logger.info(f"分类完成: {classified}/{total}")
        return classified

    def _classify_by_type(self, file_record: dict) -> str:
        ft = file_record.get('file_type', 'other')
        return FILE_TYPE_NAMES.get(ft, '其他')

    def _classify_by_date(self, file_record: dict) -> Optional[str]:
        mtime = file_record.get('modify_time')
        if not mtime:
            mtime = file_record.get('create_time')
        if not mtime:
            return None
        dt = parse_datetime_safe(mtime)
        if dt is None:
            return None
        return dt.strftime('%Y年%m月')

    def _load_db_rules(self) -> list:
        """从数据库加载已启用的分类规则（懒加载 + 缓存）
        返回: [(target_category, [keyword1, keyword2, ...]), ...]
        """
        if self._db_rules_cache is not None:
            return self._db_rules_cache
        try:
            rules = self.rule_dao.get_enabled()
            parsed = []
            for rule in rules:
                # rule_pattern 格式: "关键词1|关键词2|关键词3"
                keywords = [kw.strip() for kw in rule['rule_pattern'].split('|') if kw.strip()]
                if keywords:
                    parsed.append((rule['target_category'], keywords))
            self._db_rules_cache = parsed
            logger.info(f"从数据库加载了 {len(parsed)} 条分类规则")
        except Exception as e:
            logger.warning(f"加载数据库分类规则失败: {e}")
            self._db_rules_cache = []
        return self._db_rules_cache

    def invalidate_rules_cache(self):
        """清除规则缓存（当用户修改规则后调用）"""
        self._db_rules_cache = None

    def _classify_by_rules(self, file_record: dict) -> List[Tuple[str, float]]:
        """基于内置规则和数据库自定义规则进行分类"""
        file_name = file_record.get('file_name', '')
        file_path = file_record.get('file_path', '')
        name_lower = file_name.lower()
        path_lower = file_path.lower()
        results: List[Tuple[str, float]] = []
        matched_categories = set()  # 避免同一分类重复添加

        # ── 内置规则表 ──
        builtin_rules = [
            # (分类名, 匹配关键词列表, 匹配范围)
            ("照片", ["img_", "dsc_", "相机", "截图", "screenshot", "微信图片", "qq图片"], "name"),
            ("办公文档", ["合同", "简历", "报告", "ppt", "word", "excel", "pdf", "docx", "xlsx"], "name"),
            ("安装包", ["setup", "install", "msi", "exe安装", "下载程序"], "name"),
            ("压缩包", [".zip", ".rar", ".7z", ".tar.gz", ".iso"], "name"),
            ("视频素材", ["剪辑", "素材", "片头", "片尾", "字幕", "template"], "name"),
            ("桌面文件", ["桌面", "desktop"], "path"),
            ("下载文件", ["下载", "download", "torrent", "迅雷", "bt"], "path"),
            ("音乐", [".mp3", ".flac", ".wav", ".aac", "专辑", "歌手"], "name"),
            ("备份", ["备份", "backup", "存档", "archive"], "name"),
        ]

        for category, keywords, scope in builtin_rules:
            if category in matched_categories:
                continue
            target = path_lower if scope == "path" else name_lower
            for kw in keywords:
                if kw in target:
                    conf = min(0.5 + len(kw) * 0.06, 0.95)
                    results.append((category, conf))
                    matched_categories.add(category)
                    break

        # ── 数据库自定义规则 ──
        db_rules = self._load_db_rules()
        for target_category, keywords in db_rules:
            if target_category in matched_categories:
                continue
            # 数据库规则默认对文件名和路径都匹配
            for kw in keywords:
                kw_lower = kw.lower()
                if kw_lower in name_lower or kw_lower in path_lower:
                    conf = min(0.5 + len(kw) * 0.06, 0.95)
                    results.append((target_category, conf))
                    matched_categories.add(target_category)
                    break

        return results

    def get_classification_tree(self) -> dict:
        """获取分类树结构用于UI展示"""
        tree: dict = {}

        # 按类型
        type_items = self.cls_dao.get_distinct_values('by_type')
        tree['按类型'] = [(item['classification_value'], item['cnt']) for item in type_items]

        # 按日期
        date_items = self.cls_dao.get_distinct_values('by_date')
        tree['按日期'] = [(item['classification_value'], item['cnt']) for item in date_items]

        # 按关键词
        kw_items = self.cls_dao.get_distinct_values('by_keyword')
        tree['按关键词'] = [(item['classification_value'], item['cnt']) for item in kw_items]

        return tree
