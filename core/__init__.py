# core/__init__.py - 统一导出
# noqa: F401 — pyflakes 认为 re-export 是未使用，实际是给 ui 层用的

from core.file_scanner import FileScanWorker, get_file_type, calculate_hash, is_hidden_file
from core.file_classifier import FileClassifier
from core.file_manager import FileManager
from core.dedup_manager import DedupManager
from core.metadata_extractor import extract_metadata, extract_image_metadata, extract_pdf_metadata, extract_video_metadata
from core.operation_history import OperationHistoryManager
from core.tag_manager import TagManager
