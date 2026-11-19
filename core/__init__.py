# core/__init__.py - 统一导出
# 改为惰性导出（PEP 562）：导入 core 不再级联加载 file_scanner/file_watcher 的 PyQt6 依赖，
# 使扫描/哈希等纯计算模块可在无 Qt 环境下测试与测量。
import importlib

_EXPORTS = {
    'FileScanWorker': 'core.file_scanner',
    'get_file_type': 'core.file_scanner',
    'calculate_hash': 'core.file_scanner',
    'is_hidden_file': 'core.file_scanner',
    'FileClassifier': 'core.file_classifier',
    'FileManager': 'core.file_manager',
    'DedupManager': 'core.dedup_manager',
    'extract_metadata': 'core.metadata_extractor',
    'OperationHistoryManager': 'core.operation_history',
    'TagManager': 'core.tag_manager',
    'DirectoryWatcher': 'core.file_watcher',
    'NLSearchParser': 'core.rule_engine',
    'TagRecommender': 'core.rule_engine',
    'CleanupAdvisor': 'core.rule_engine',
    'TaskManager': 'core.task_manager',
    'IndexHealthService': 'core.index_health',
    'AppDataResetService': 'core.data_reset',
    'AIModelConfigManager': 'core.ai_model_config',
}

__all__ = list(_EXPORTS)


def __getattr__(name):
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
    value = getattr(importlib.import_module(module_name), name)
    globals()[name] = value  # 缓存，后续访问不再走 __getattr__
    return value


def __dir__():
    return sorted(__all__)
