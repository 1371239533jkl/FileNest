"""
文件变化监控 - 使用 watchdog 监控已扫描目录的变化
"""
import os
import threading
from typing import Optional
from PyQt6.QtCore import QObject, pyqtSignal, QTimer, Qt, QMetaObject, QThread

from utils.logger import logger


class FileChangeEvent:
    """文件变化事件"""
    
    def __init__(self, event_type: str, path: str, is_directory: bool = False,
                 dest_path: str = ''):
        self.event_type = event_type  # 'created', 'modified', 'deleted', 'moved'
        self.path = path
        self.is_directory = is_directory
        self.dest_path = dest_path  # moved 事件的目标路径
    
    def __repr__(self):
        if self.dest_path:
            return f"FileChangeEvent({self.event_type}, {self.path} -> {self.dest_path})"
        return f"FileChangeEvent({self.event_type}, {self.path})"


class DirectoryWatcher(QObject):
    """目录变化监控器
    
    使用 watchdog 库监控已扫描目录的文件变化，
    当检测到变化时发出信号通知 UI 层。
    """
    
    files_changed = pyqtSignal(list)  # 发出变化事件列表
    monitoring_started = pyqtSignal()
    monitoring_stopped = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._observer = None
        self._watched_dirs = set()
        self._pending_events = []
        self._events_lock = threading.Lock()
        # QTimer 延迟到 start() 中创建，确保在主线程中
        self._debounce_timer = None
        self._enabled = False
    
    def start(self, directories: list):
        """开始监控指定的目录列表
        
        Args:
            directories: 要监控的目录路径列表
        """
        if self._observer is not None:
            self.stop()
        
        if not directories:
            logger.debug("没有目录需要监控")
            return
        
        # 在主线程中创建 QTimer（避免跨线程问题）
        if self._debounce_timer is None:
            self._debounce_timer = QTimer()
            self._debounce_timer.setInterval(2000)  # 2秒防抖
            self._debounce_timer.setSingleShot(True)
            self._debounce_timer.timeout.connect(self._flush_events)
        
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
            
            class Handler(FileSystemEventHandler):
                def __init__(self, watcher):
                    self._watcher = watcher
                
                def on_created(self, event):
                    self._watcher._on_event('created', event)
                
                def on_modified(self, event):
                    self._watcher._on_event('modified', event)
                
                def on_deleted(self, event):
                    self._watcher._on_event('deleted', event)
                
                def on_moved(self, event):
                    self._watcher._on_event('moved', event)
            
            self._observer = Observer()
            handler = Handler(self)
            
            for dir_path in directories:
                if os.path.isdir(dir_path):
                    self._observer.schedule(handler, dir_path, recursive=True)
                    self._watched_dirs.add(dir_path)
                    logger.debug(f"开始监控目录: {dir_path}")
            
            if not self._watched_dirs:
                logger.debug("没有有效的监控目录")
                return
            
            self._observer.start()
            self._enabled = True
            self.monitoring_started.emit()
            logger.info(f"已启动文件监控，共 {len(self._watched_dirs)} 个目录")
            
        except ImportError:
            logger.warning("watchdog 库未安装，文件变化监控不可用")
        except Exception as e:
            logger.error(f"启动文件监控失败: {e}")
    
    def stop(self):
        """停止监控所有目录"""
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=3)
            except Exception as e:
                logger.warning(f"停止监控异常: {e}")
            self._observer = None
            self._watched_dirs.clear()
            with self._events_lock:
                self._pending_events.clear()
            self._enabled = False
            self.monitoring_stopped.emit()
            logger.info("已停止文件监控")
    
    def is_running(self) -> bool:
        """返回监控是否正在运行"""
        return self._observer is not None and self._enabled
    
    def _on_event(self, event_type: str, event):
        """处理 watchdog 事件（在工作线程中）"""
        if event.is_directory:
            return  # 忽略目录变化，只关注文件
        
        path = event.src_path
        if self._is_ignored(path):
            return
        
        dest_path = ''
        if event_type == 'moved':
            dest_path = getattr(event, 'dest_path', '') or ''
            if self._is_ignored(dest_path):
                return
        
        evt = FileChangeEvent(event_type, path, event.is_directory, dest_path)
        with self._events_lock:
            self._pending_events.append(evt)
        
        # 使用 QMetaObject.invokeMethod 将 QTimer 启动调度到主线程
        # 因为 QTimer 不能在非 GUI 线程中启动
        if self._debounce_timer:
            QMetaObject.invokeMethod(
                self._debounce_timer, 
                "start",
                Qt.ConnectionType.QueuedConnection
            )
    
    def _flush_events(self):
        """防抖结束后发出累积的事件"""
        with self._events_lock:
            if not self._pending_events:
                return
            events = list(self._pending_events)
            self._pending_events.clear()
        
        logger.debug(f"检测到 {len(events)} 个文件变化")
        self.files_changed.emit(events)
    
    def _is_ignored(self, path: str) -> bool:
        """检查路径是否应被忽略"""
        # 忽略常见的临时文件和隐藏文件
        ignored_patterns = [
            '.git', '__pycache__', '.pytest_cache',
            '.trash', '.DS_Store', 'Thumbs.db',
            '~$', '.tmp', '.swp',
        ]
        basename = os.path.basename(path)
        return any(p in path or basename.startswith(p) for p in ignored_patterns)


class WatcherManager:
    """全局监控管理器（单例）
    
    管理文件监控的启动/停止，并协调与 UI 的交互。
    """
    
    _instance: Optional['WatcherManager'] = None
    
    def __init__(self):
        self._watcher = DirectoryWatcher()
        self._auto_scan_enabled = False
        self._scan_callback = None
        self._apply_worker = None
        self._auto_apply_enabled = False
        self._apply_done_callback = None
    
    @classmethod
    def get_instance(cls) -> 'WatcherManager':
        if cls._instance is None:
            cls._instance = WatcherManager()
        return cls._instance
    
    def enable(self, directories: list, scan_callback=None,
               auto_apply: bool = False, apply_done_callback=None):
        """启用文件监控
        
        Args:
            directories: 要监控的目录列表
            scan_callback: 当检测到变化时调用的函数（通常触发扫描）
            auto_apply: 是否自动将文件变化增量落库（索引自动更新）
            apply_done_callback: 增量落库完成后回调（接收统计 dict）
        """
        self._scan_callback = scan_callback
        self._auto_apply_enabled = auto_apply
        self._apply_done_callback = apply_done_callback
        self._watcher.files_changed.connect(self._on_files_changed)
        self._watcher.start(directories)
        self._auto_scan_enabled = True
    
    def disable(self):
        """禁用文件监控"""
        self._watcher.stop()
        self._auto_scan_enabled = False
        self._auto_apply_enabled = False
        self._apply_done_callback = None
        if self._apply_worker is not None:
            try:
                self._apply_worker.cancel()
                self._apply_worker.wait(2000)
            except Exception:
                pass
            self._apply_worker = None
        try:
            self._watcher.files_changed.disconnect()
        except TypeError:
            pass
    
    def is_active(self) -> bool:
        return self._watcher.is_running()
    
    def _on_files_changed(self, events: list):
        """处理文件变化事件"""
        if not self._auto_scan_enabled or not events:
            return
        
        if self._auto_apply_enabled:
            self._start_apply_events(events)
            return
        
        created = [e for e in events if e.event_type == 'created']
        modified = [e for e in events if e.event_type == 'modified']
        deleted = [e for e in events if e.event_type == 'deleted']
        
        summary = []
        if created:
            summary.append(f"新增 {len(created)} 个")
        if modified:
            summary.append(f"修改 {len(modified)} 个")
        if deleted:
            summary.append(f"删除 {len(deleted)} 个")
        
        logger.info(f"文件变化: {', '.join(summary)}")
        
        if (created or modified or deleted) and self._scan_callback:
            logger.info("检测到文件变化，通知上层同步...")
            self._scan_callback()
    
    def _start_apply_events(self, events: list):
        """在后台线程执行增量落库，完成后回调。"""
        if self._apply_worker is not None and self._apply_worker.isRunning():
            logger.debug("增量落库线程正忙，丢弃本次事件批次")
            return
        from core.index_updater import IncrementalIndexUpdater
        self._apply_worker = _ApplyEventsWorker(events, IncrementalIndexUpdater())
        self._apply_worker.finished_ok.connect(self._on_apply_done)
        self._apply_worker.start()
    
    def _on_apply_done(self, stats: dict):
        self._apply_worker = None
        logger.info(f"增量落库完成: applied={stats['applied']}, failed={stats['failed']}")
        if self._apply_done_callback:
            self._apply_done_callback(stats)


class _ApplyEventsWorker(QThread):
    """后台增量落库线程"""
    finished_ok = pyqtSignal(dict)
    
    def __init__(self, events: list, updater, parent=None):
        super().__init__(parent)
        self._events = events
        self._updater = updater
        self._cancelled = False
    
    def cancel(self):
        self._cancelled = True
    
    def run(self):
        if self._cancelled:
            return
        try:
            stats = self._updater.apply(self._events)
            if not self._cancelled:
                self.finished_ok.emit(stats)
        except Exception as exc:
            logger.error(f"增量落库线程异常: {exc}")
            self.finished_ok.emit({'applied': 0, 'failed': len(self._events),
                                   'errors': [str(exc)]})
