"""
标签管理器 - 文件标签的增删查
"""

from database.db_manager import db
from database.models import TagDAO
from utils.logger import logger


class TagManager:
    """文件标签管理器"""

    def __init__(self):
        self.tag_dao = TagDAO(db)

    def add_tag(self, file_id: int, tag_name: str) -> bool:
        """给文件打标签"""
        try:
            return self.tag_dao.add_tag(file_id, tag_name) > 0
        except Exception as e:
            logger.warning(f"打标签失败 file_id={file_id}: {e}")
            return False

    def create_tag(self, tag_name: str) -> bool:
        """创建独立标签（不关联文件）"""
        try:
            return self.tag_dao.create_tag(tag_name) > 0
        except Exception as e:
            logger.warning(f"创建标签失败: {e}")
            return False

    def remove_tag(self, file_id: int, tag_name: str) -> bool:
        """移除文件标签"""
        try:
            return self.tag_dao.remove_tag(file_id, tag_name) > 0
        except Exception as e:
            logger.warning(f"移除标签失败 file_id={file_id}: {e}")
            return False

    def batch_add_tags(self, file_ids: list, tag_names: list) -> int:
        """批量给多个文件加多个标签"""
        try:
            return self.tag_dao.batch_add_tags(file_ids, tag_names)
        except Exception as e:
            logger.warning(f"批量打标签失败: {e}")
            return 0

    def get_tags_by_file(self, file_id: int) -> list:
        """获取文件的所有标签"""
        return self.tag_dao.get_tags_by_file(file_id)

    def get_files_by_tag(self, tag_name: str) -> list:
        """获取某个标签的所有文件"""
        return self.tag_dao.get_files_by_tag(tag_name)

    def get_all_tags(self) -> list:
        """获取所有标签及计数"""
        return self.tag_dao.get_all_tags()

    def get_all_tags_by_file(self, file_ids: list) -> dict:
        """批量查多个文件的标签"""
        return self.tag_dao.get_all_tags_by_file(file_ids)

    def rename_tag(self, old_name: str, new_name: str) -> bool:
        """重命名标签"""
        try:
            return self.tag_dao.rename_tag(old_name, new_name) > 0
        except Exception as e:
            logger.warning(f"重命名标签失败: {e}")
            return False

    def delete_tag(self, tag_name: str) -> bool:
        """删除标签（从所有文件移除）"""
        try:
            return self.tag_dao.delete_tag(tag_name) > 0
        except Exception as e:
            logger.warning(f"删除标签失败: {e}")
            return False
