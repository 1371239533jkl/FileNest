"""
Smart File Manager HTTP API 服务（批次7 P2-09 自动化开放接口）。

零侵入设计：只新增、不修改 —— 不 import 任何 UI 模块，不改 core/database/config，
本机 GUI 与 CLI 的使用完全不受影响。数据库默认沿用 config.DB_PATH，
服务器部署时通过环境变量 SFM_DB 指向独立数据库（需在服务器上重新扫描建索引，
索引记录的是服务器本机绝对路径，不要直接拷贝本地数据库过来）。

环境变量（全部可选）：
    SFM_API_KEY   API 密钥；设置后所有 /api/* 请求需带 X-API-Key 请求头
    SFM_DB        数据库路径覆盖（服务器独立库，避免与本地数据混淆）
    SFM_HOST      监听地址，默认 127.0.0.1（仅本机；对外服务设为 0.0.0.0）
    SFM_PORT      监听端口，默认 8765

服务器部署步骤：
    1. 拷贝代码到服务器，安装依赖：
         pip install -r requirements.txt fastapi uvicorn
    2. 启动（示例，Windows 用 set / Linux 用 export）：
         set SFM_API_KEY=your-secret
         set SFM_DB=/srv/sfm/sfm.db
         set SFM_HOST=0.0.0.0
         python server.py
    3. 在服务器上重建索引：
         curl -X POST http://127.0.0.1:8765/api/scan ^
              -H "X-API-Key: your-secret" ^
              -H "Content-Type: application/json" ^
              -d "{\"directory\": \"/data/docs\", \"recursive\": true}"
    4. 客户端通过 http://<服务器IP>:8765/api/search 等端点访问。

端点：
    GET    /health                      健康检查（免鉴权）
    POST   /api/scan                    扫描目录建索引 {directory, recursive}
    GET    /api/search                  搜索 name/type/ext/min_size/max_size/limit
    GET    /api/files/{file_id}         文件详情
    GET    /api/tags                    全部标签
    GET    /api/files/{file_id}/tags    文件标签
    POST   /api/files/{file_id}/tags    添加标签 {tag}
    DELETE /api/files/{file_id}/tags    移除标签 {tag}
    GET    /api/lifecycle/check         生命周期策略检查（只读匹配结果）
    POST   /api/lifecycle/run/{id}      执行策略（remind 直接放行；
                                       archive/trash 需 body {"confirm": true}）

安全设计：
    - 默认只绑定 127.0.0.1，需要对外服务才显式设置 SFM_HOST=0.0.0.0
    - API Key：监听本机时可省略；对外监听（非回环 SFM_HOST）时必须设置
      SFM_API_KEY，否则拒绝启动（见 _require_api_key_for_external_host）
    - 所有写操作复用现有安全链路：标签走 TagManager 校验与审计，
      生命周期走回收区 + 操作历史，无物理删除
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 环境变量需在 import config / db 之前生效（与 cli.py --db 覆盖方式一致）
if os.environ.get('SFM_DB'):
    import config
    config.DB_PATH = os.environ['SFM_DB']

# 服务器无 GUI 环境：core 包初始化会级联导入 file_scanner/file_watcher 等
# 模块级 PyQt6 导入（仅类定义需要）。缺失时注入轻量桩模块保证 import 通过；
# 本地装有 PyQt6 时走真实导入，行为不变。server 自身不使用任何 Qt 功能。
try:
    import PyQt6.QtCore  # noqa: F401
except ImportError:
    import types
    _qtcore = types.ModuleType('PyQt6.QtCore')
    _qtcore.QThread = type('QThread', (), {})
    _qtcore.QObject = type('QObject', (), {})
    _qtcore.QTimer = type('QTimer', (), {})
    _qtcore.Qt = type('Qt', (), {})
    _qtcore.QMetaObject = type('QMetaObject', (), {})
    _qtcore.pyqtSignal = lambda *args, **kwargs: None
    _pyqt6 = types.ModuleType('PyQt6')
    _pyqt6.QtCore = _qtcore
    sys.modules['PyQt6'] = _pyqt6
    sys.modules['PyQt6.QtCore'] = _qtcore

import io
import json
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config import APP_VERSION, FILE_TYPES
from database.db_manager import db
from database.models import (
    FileDAO, TagDAO, LifecyclePolicyDAO, MetadataDAO, ClassificationDAO,
    VersionRelationDAO,
)
from core.scan_service import ScanService
from core.tag_manager import TagManager
from core.task_runner import TaskRunner
from core.lifecycle_service import LifecycleService
from web_api import router as web_router

@asynccontextmanager
async def _lifespan(_app: FastAPI):
    _require_api_key_for_external_host(os.environ.get('SFM_HOST', '127.0.0.1'))
    db.init_database()
    yield


app = FastAPI(title='Smart File Manager API', version='0.1.0',
              lifespan=_lifespan)

API_KEY = os.environ.get('SFM_API_KEY', '')

_LOOPBACK_HOSTS = {'127.0.0.1', 'localhost', '::1'}


def _require_api_key_for_external_host(host: str):
    """对外监听（非回环地址）时必须设置 SFM_API_KEY。

    否则所有 /api/* 接口匿名可访问（含文件删除、AI 配置写入）；
    宁可拒绝启动，也不静默暴露。
    """
    if host and host not in _LOOPBACK_HOSTS and not API_KEY:
        raise RuntimeError(
            f"拒绝启动：SFM_HOST={host} 对外监听但未设置 SFM_API_KEY，"
            "接口将匿名可访问。请设置 SFM_API_KEY，或改回 127.0.0.1。")


def _auth(x_api_key: Optional[str]):
    """API Key 鉴权：未设置 SFM_API_KEY 时不校验（默认仅本机监听）。"""
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail='无效的 API Key')


# ── 请求模型 ──────────────────────────────────────────────────

class ScanReq(BaseModel):
    directory: str
    recursive: bool = True


class TagReq(BaseModel):
    tag: str


class LifecycleRunReq(BaseModel):
    confirm: bool = False


# ── 免鉴权 ────────────────────────────────────────────────────

@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'smart-file-manager',
            'version': APP_VERSION, 'pid': os.getpid()}


# ── 扫描 / 搜索 / 详情 ───────────────────────────────────────

@app.post('/api/scan')
def scan(req: ScanReq, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    directory = req.directory
    if not os.path.isdir(directory):
        raise HTTPException(status_code=400, detail=f'目录不存在: {directory}')

    result = ScanService(db).scan(
        directory, recursive=req.recursive, compute_hash=False)
    return {'indexed': result['written'], 'skipped': 0, 'errors': [],
            'elapsed_s': result['elapsed_s']}


# ── 后台任务（T1-2）：长任务 + SSE 进度 ─────────────────────────
TASKS = TaskRunner()


class ScanStartReq(BaseModel):
    directory: str
    recursive: bool = True
    compute_hash: bool = True


@app.post('/api/scan/start')
def scan_start(req: ScanStartReq, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    if not os.path.isdir(req.directory):
        raise HTTPException(status_code=400, detail=f'目录不存在: {req.directory}')

    def job(progress, cancel_event):
        return ScanService(db).scan(
            req.directory, recursive=req.recursive,
            compute_hash=req.compute_hash,
            progress=progress, cancel=cancel_event.is_set)

    task = TASKS.submit(f'scan:{req.directory}', job)
    return {'task_id': task.id}


@app.post('/api/dedup/start')
def dedup_start(reset: bool = False, x_api_key: Optional[str] = Header(None)):
    """多阶段重复检测：按大小 → 快速哈希 → 完整哈希分组，结果写回 files 表。"""
    _auth(x_api_key)

    def job(progress, cancel_event):
        from core.multistage_dedup import MultistageDedupDetector

        def on_stage(_stage, current, total, _path):
            progress(current, total)

        return MultistageDedupDetector().run(
            progress_cb=on_stage,
            reset=reset,
            cancel_check=cancel_event.is_set,
        )

    task = TASKS.submit('dedup', job)
    return {'task_id': task.id}


@app.post('/api/scan/cancel')
def scan_cancel(task_id: int, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    if not TASKS.cancel(task_id):
        raise HTTPException(status_code=404, detail='任务不存在或已结束')
    return {'cancelled': True}


@app.get('/api/tasks')
def task_list(x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    return TASKS.snapshot()


@app.get('/api/tasks/{task_id}')
def task_detail(task_id: int, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    task = TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail='任务不存在')
    return task


@app.get('/api/thumb')
def thumb(path: str, size: int = 256, x_api_key: Optional[str] = Header(None)):
    """返回缩略图 JPEG（解码即缩放，不输出原图）。"""
    _auth(x_api_key)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail='文件不存在')
    if os.path.splitext(path)[1].lower() not in FILE_TYPES['image']:
        raise HTTPException(status_code=400, detail='不是支持的图片格式')
    size = max(16, min(size, 1024))
    try:
        from PIL import Image
        with Image.open(path) as img:
            img.thumbnail((size, size))
            buf = io.BytesIO()
            img.convert('RGB').save(buf, 'JPEG', quality=82)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f'生成缩略图失败: {exc}')
    return Response(content=buf.getvalue(), media_type='image/jpeg',
                    headers={'Cache-Control': 'max-age=3600'})


@app.post('/api/shutdown')
def shutdown(x_api_key: Optional[str] = Header(None)):
    """优雅退出：先回响应，再结束进程（WAL 已提交的数据不受影响）。"""
    _auth(x_api_key)
    threading.Timer(0.3, os._exit, (0,)).start()
    return {'ok': True}


@app.get('/api/events')
def events(x_api_key: Optional[str] = Header(None)):
    """SSE 推送任务快照；没有运行中任务时发一帧后关闭，客户端按需重连。"""
    _auth(x_api_key)

    def stream():
        while True:
            snapshot = TASKS.snapshot()
            yield 'data: ' + json.dumps(snapshot, ensure_ascii=False) + '\n\n'
            if not snapshot['running']:
                return
            time.sleep(0.3)

    return StreamingResponse(
        stream(), media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache'})


@app.get('/api/search')
def search(name: Optional[str] = None, type: Optional[str] = None,
           ext: Optional[str] = None, min_size: Optional[int] = None,
           max_size: Optional[int] = None, limit: int = 50,
           x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    results = FileDAO(db).search(
        name=name, file_type=type, extension=ext,
        min_size=min_size, max_size=max_size) or []
    items = [{
        'id': r['id'], 'file_name': r['file_name'], 'file_path': r['file_path'],
        'file_size': r['file_size'], 'file_type': r.get('file_type', ''),
        'modify_time': r.get('modify_time', ''),
    } for r in results[:max(0, limit)]]
    return {'total': len(items), 'items': items}


def _content_excerpt(file_id: int) -> Optional[str]:
    """从全文索引取内容摘录（FTS 表可能未建，降级返回 None）。"""
    try:
        row = db.execute_one(
            "SELECT snippet(file_content_fts, 1, '[', ']', '...', 18) AS s "
            "FROM file_content_fts WHERE file_id = ?", (file_id,))
        if row and row.get('s'):
            return row['s']
        row = db.execute_one(
            "SELECT substr(content, 1, 200) AS s "
            "FROM file_content_fts WHERE file_id = ?", (file_id,))
        return row.get('s') if row else None
    except Exception:  # noqa: BLE001 FTS 表未建
        return None


@app.get('/api/files/{file_id}')
def file_detail(file_id: int, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    rec = FileDAO(db).get_by_id(file_id)
    if not rec:
        raise HTTPException(status_code=404, detail='文件不存在')
    result = dict(rec)
    for k in ('create_time', 'modify_time', 'scan_time'):
        if result.get(k):
            result[k] = result[k].strftime('%Y-%m-%d %H:%M:%S') \
                if hasattr(result[k], 'strftime') else result[k]
    result['tags'] = [t['tag_name'] for t in TagDAO(db).get_tags_by_file(file_id)]
    result['classifications'] = ClassificationDAO(db).get_by_file_id(file_id) or []
    result['metadata'] = MetadataDAO(db).get_by_file_id(file_id) or None
    result['relations'] = VersionRelationDAO(db).get_relations_for_file(file_id) or []
    result['content_excerpt'] = _content_excerpt(file_id)
    return result


# ── 标签 ──────────────────────────────────────────────────────

@app.get('/api/tags')
def all_tags(x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    tags = TagDAO(db).get_all_tags() or []
    return {'total': len(tags), 'tags': [t['tag_name'] for t in tags]}


@app.get('/api/files/{file_id}/tags')
def file_tags(file_id: int, x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    tags = TagDAO(db).get_tags_by_file(file_id) or []
    return {'file_id': file_id, 'tags': [t['tag_name'] for t in tags]}


@app.post('/api/files/{file_id}/tags')
def add_tag(file_id: int, req: TagReq,
            x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    ok = TagManager().add_tag(file_id, req.tag)
    if not ok:
        raise HTTPException(status_code=400, detail='添加标签失败（文件未索引或已存在）')
    return {'file_id': file_id, 'tag': req.tag, 'success': True}


@app.delete('/api/files/{file_id}/tags')
def remove_tag(file_id: int, req: TagReq,
               x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    ok = TagManager().remove_tag(file_id, req.tag)
    if not ok:
        raise HTTPException(status_code=400, detail='移除标签失败')
    return {'file_id': file_id, 'tag': req.tag, 'success': True}


# ── 生命周期 ──────────────────────────────────────────────────

@app.get('/api/lifecycle/check')
def lifecycle_check(x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    results = LifecycleService().check_all()
    items = []
    for r in results:
        p = r['policy']
        items.append({
            'id': p.get('id'), 'name': p.get('name'),
            'action': p.get('action'), 'target_type': p.get('target_type'),
            'target_value': p.get('target_value'),
            'days_threshold': p.get('days_threshold'),
            'match_count': r['match_count'],
        })
    return {'total': len(items), 'items': items}


@app.post('/api/lifecycle/run/{policy_id}')
def lifecycle_run(policy_id: int, req: LifecycleRunReq,
                  x_api_key: Optional[str] = Header(None)):
    _auth(x_api_key)
    service = LifecycleService()
    policy = service.policy_dao.get_by_id(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail='策略不存在')
    if policy.get('action') in ('archive', 'trash') and not req.confirm:
        raise HTTPException(
            status_code=400,
            detail='该策略动作会改动文件，需 body {"confirm": true} 确认后再执行')
    matches = service.match_files(policy)
    result = service.execute(policy, matches)
    return {
        'policy_id': policy_id,
        'match_count': len(matches),
        **result,
    }


# ── Web 管理界面（批次8 Web 化）────────────────────────────
# 挂载完整业务 API 与静态 SPA；不影响现有端点与桌面端。
app.include_router(web_router)

_WEBAPP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'webapp')
if os.path.isdir(_WEBAPP_DIR):
    from fastapi.staticfiles import StaticFiles
    app.mount('/', StaticFiles(directory=_WEBAPP_DIR, html=True),
              name='webapp')


if __name__ == '__main__':
    import uvicorn
    host = os.environ.get('SFM_HOST', '127.0.0.1')
    _require_api_key_for_external_host(host)
    uvicorn.run(app, host=host,
                port=int(os.environ.get('SFM_PORT', '8765')))
