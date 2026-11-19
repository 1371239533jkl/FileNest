# FileNest 重构方案与实施方案 v3.0

**【方案A】Electron + Vue 3 + TypeScript + Python sidecar**

| 项目 | 内容 |
|------|------|
| 文档版本 | 3.0（取代 2.0） |
| 适用基线 | v2.7.0 / `c0a5b2b` |
| 状态 | 已确认方案A，待评审执行 |
| 硬约束 | 本地开箱即用、离线可用、零配置、不引入未确认新技术 |
| 文中标记 | `【A】` = 方案A专属内容；`〔待确认〕` = 需评审拍板的选型（当前选型已全部确认，无待定项） |

---

## 0. 阅读指引

本文档分两部分：

- **第 1–6 章 = 重构方案**（做什么、为什么、目标形态）
- **第 7–11 章 = 实施方案**（谁做、何时做、怎么验、怎么退）

`【A】` 标记的章节为方案A（Electron + Vue3 + TS + Python sidecar）的专属设计，其余章节（现状分析、数据层治理、测试策略、风险控制）对任意技术栈都成立。

---

# 第一部分：重构方案

## 1. 决策摘要

### 1.1 已确认事项

| 项 | 决策 |
|----|------|
| 画面层 | 【A】**Electron（Chromium 自带）+ Vue 3 + TypeScript**，100% 不经过 Python |
| 业务层 | 【A】**Python 保持为本地 sidecar 服务**，无 Qt，仅 AI/解析/数据/文件操作 |
| 计算层 | **仍用 Python**，通过标准库多进程获得真并行（不引入 Rust/Node 原生模块） |
| 数值计算 | **numpy**：向量检索（矩阵化）、相似分组（分块汉明）、dHash 位打包；不替代多进程 |
| 数据层 | **SQLite 保留**，Python 为唯一写者，事务批量化 + keyset 分页 |
| 移除 | PyQt6 与全部 QWidget 界面代码 |

### 1.2 三条主线

| 主线 | 内容 | 主要收益 |
|------|------|----------|
| **M1 画面重写**【A】 | Vue 3 组件化重写 10 个页面，Electron 壳承载 | 观感、滚动流畅度、主题切换、开发迭代速度 |
| **M2 服务化** | Python 去 Qt、FastAPI 统一入口、sidecar 生命周期管理 | 故障隔离、可测试、可 CLI/远程复用 |
| **M3 数据与计算治理** | 事务批量化、keyset 分页、索引补齐、多进程并行 | 规模吞吐（2.5–8×），且不依赖换语言 |

### 1.3 与备选方案的取舍（详见第 5 章）

| 方案 | 结论 | 核心理由 |
|------|------|----------|
| 【A】Electron + Vue3 + TS + Python | **采用** | 语言最少（2 门）、自带 Chromium 真开箱即用、Vue/TS 已具备 |
| B：Tauri + Vue3 + Rust + Python | 否决 | 多一门 Rust；体积优势仅在依赖系统 WebView 时成立 |
| C：QML + Rust + Python | 否决 | 需重学 QML + Rust，且 UI 精细度靠手工堆 |
| D：JavaFX + Python | 否决 | 观感上限低于 Web，且用不上 Vue 能力 |

### 1.4 明确不引入（避免范围蔓延）

Rust / napi-rs、Qt / QML、Tauri、Redis、向量数据库、服务端数据库、微服务框架、Electron 之外的桌面框架。

> 计算加速不引入新语言：Python 标准库 `concurrent.futures.ProcessPoolExecutor` 即可绕开 GIL 实现多核并行（详见 §5.3）。

### 1.5 节奏

P0 度量与骨架（1.5 周）→ P1 服务化与数据治理（3 周）→ P2 渲染骨架与设计系统（3 周，与 P1 重叠 1 周）→ P3 页面迁移（6 周）→ P4 收尾与发布（2.5 周）＝ **16 周**，含 10% 缓冲约 **17.5 周**。

### 1.6 技术栈清单

| 类别 | 项 | 状态 |
|------|----|------|
| 沿用 | Python 3.x、SQLite（WAL + FTS5）、FastAPI + uvicorn、Pillow、PyMuPDF、python-docx、python-pptx、watchdog、Pygments、pytest | 不变 |
| 新增（A 必需） | Electron、Vue 3、TypeScript、Vite、electron-builder | 已确认 |
| 新增（本次评审确认） | **ECharts**（按需引入 + 懒加载）、**markdown-it**（`html:false`）、**DOMPurify** | 已确认 |
| 新增（本次评审确认） | **numpy**（向量检索 / 相似分组 / 位打包；仅数值层，不接管 IO） | 已确认 |
| 不引入 | Rust / napi-rs、Qt / QML、Tauri、Redis、向量数据库、服务端数据库、前端代码高亮库（shiki / highlight.js）、scipy / pandas / faiss | 明确排除 |

> 新增项均为 MIT / Apache-2.0 / BSD 许可，与项目 MIT 兼容；版本须锁定并纳入季度依赖审计（见 R11）。
>
> numpy 前置条件（P0 验证）：Python 3.14 下 wheel 可用；PyInstaller 打包后体积增量约 15–20MB（计入 §2.3 体积预算）；不可用时保留纯 Python 回退路径。



---

## 2. 重构目标与范围

### 2.1 目标（可验收）

| 编号 | 目标 | 验收口径 |
|------|------|----------|
| G1 | 画面与流畅度 | 全页面 Vue 实现；10 万条列表滚动帧时 p95 ≤ 16.7ms；主题切换 ≤ 120ms |
| G2 | 启动体验 | 首帧 ≤ 400ms（Electron 特性上限所限）；可交互 ≤ 1.5s；sidecar 就绪 ≤ 1.2s |
| G3 | 批量吞吐 | 扫描 ≥ 2.5×、哈希 ≥ 2×、dHash ≥ 3×、语义检索 p95 ≤ 50ms、相似分组 ≤ 400ms（相对 P0 基线） |
| G4 | 故障隔离 | sidecar 崩溃不影响界面，可自动重启（≤ 2 次）；界面崩溃不损坏数据库 |
| G5 | 可维护性 | 单文件 ≤ 500 行；`QThread` 子类归零；内联样式归零；UI 与业务零直接依赖 |
| G6 | 平稳过渡 | 功能对等清单 100%；旧库可直接打开；保留上一版可回退 |

> G1/G3 的目标值低于此前 Rust 方案的预期，这是方案A"不引入新语言"的**自觉取舍**，不是能力缺失（理由见 §5.3）。

### 2.2 范围

**纳入**

- `ui/` 全量重写为 Vue 组件（16,825 行 → 目标 ≤ 10,000 行 TS/Vue）
- 【A】Electron 主进程、preload 桥、打包与签名
- `core/` 去 Qt 化、`web_api.py` 扩展为 sidecar API、`server.py` 成为唯一服务入口
- `database/` 事务、分页、索引、迁移版本
- 计算多进程化与批量化
- 基准体系、CI、灰度与回滚流程

**不做（Non-Goals）**

- 不保留 PyQt6 UI（不维护双界面；v2.7 分支即回退通道）
- 不把 AI/文档解析迁出 Python
- 不做公网服务、不做多用户协作、不做 Web 主界面
- 不引入 Rust/Node 原生模块（除非 §5.3 的退出条件被触发）

### 2.3 硬约束

| 约束 | 含义 |
|------|------|
| 开箱即用 | 单安装包，自带 Chromium；不依赖系统 WebView、不要求预装 Python/Java |
| 离线优先 | 全部本地功能断网可用 |
| 体积 | **≤ 300MB 安装包**（2026-11-18 决策：接受 Electron 运行时成本。实测未压缩 539MB，估算安装包 220–270MB，见 BASELINE §3.1） |
| 首屏 JS | ≤ 300KB（gzip）；ECharts 等重依赖必须动态 `import()` 懒加载，不得进入首屏包 |
| 数据兼容 | 旧库可直接打开，只增列/加索引，禁止破坏性 DDL |
| 技术栈稳定 | 新增仅限 §1.6 清单；其余见 §1.4 |

---

## 3. 现状问题分析

### 3.1 基线数据（实测）

| 维度 | 数值 |
|------|------|
| Python 文件 / 行数 | 114 / 34,115（`ui/` 16,825，占 49%） |
| 最大单文件 | `ui/ai_chat_page.py` 2,306 行 |
| `QThread` 子类 | 30 个（18 个文件），各自实现取消/等待 |
| 内联 `setStyleSheet` | 188 处（27 个文件） |
| `ui/` 直接 import DAO | 36 处 |
| `core/` 依赖 PyQt6 | 5 个模块（scanner / watcher / batch_classifier / data_cache / task_manager） |
| 现有 HTTP 路由 | 101 个（`web_api.py`） |
| 现有 Web 前端 | 2,565 行 JS + 374 行 CSS（`webapp/`） |
| 测试 | 31 个文件，其中 11 个 import PyQt6 |
| 性能埋点 | 0 处 |
| 工程化 | 无 `pyproject.toml`/`.spec`/CI；13 个依赖全为 `>=`，无 lock；无 `schema_version` |

### 3.2 架构级问题

| 编号 | 问题 | 证据 | 后果 |
|------|------|------|------|
| S1 | 单进程单体，无演进边界 | `main.py` 单入口；`server.py:63-77` 需桩模块顶替 Qt | 故障不隔离、无法复用后端、换任一层都要动全身 |
| S2 | 分层方向倒置 | `ui/` 36 处直接 import DAO；`core/` 5 个模块 import PyQt6；11 个测试依赖 Qt | 业务与渲染框架双向耦合，"换画面"约等于"改业务" |
| S3 | 无并发调度模型 | 30 个 `QThread`；`core/task_manager.py:1-5` 仅登记状态；页面各自写 `cancel+wait`（`ui/duplicates_tab.py:211`） | 无优先级、无全局限流、无统一超时，退出卡死 |
| S4 | 渲染为"每帧重算" | `ui/chart_widgets.py:146,164`；`ui/ai_chat_page.py:256-269`；`ui/classify_tab.py:183-189,305,1541-1552` | 性能随数据量/文本长度线性恶化 |
| S5 | 无批量化边界 | `database/db_manager.py:68-96`（每语句 commit）；`core/multistage_dedup.py:136-151`（N+1）；`core/content_indexer.py:55`（全表载入）；`core/image_similarity.py:102-109`（O(n²)）；`core/embedding_service.py:39-48,80` | 规模一大即崩，且是"放大器"式恶化 |
| S6 | 零工程护栏 | 无 CI/无基准/无 schema 版本/无 lock；0 处埋点 | 无法度量、无法防回归、回滚无抓手 |
| S7 | 分发与许可不匹配 | 未见打包清单；PyQt6 为 GPLv3 而项目声明 MIT | 法律风险 + 升级/回滚无通道 |

### 3.3 换栈能解决 vs 必须单独治理

| 问题 | Vue 重写解决 | Python 治理解决 | 必须专项 |
|------|--------------|-----------------|----------|
| 画面质感、滚动、主题切换 | 是 | — | — |
| 大列表/富文本重排 | 是（虚拟滚动 + DOM 追加） | — | — |
| 每语句 commit、N+1、OFFSET 深分页 | 否 | 是 | — |
| UI 直连 DAO | 否 | 部分 | 是（契约层） |
| 30 个线程各写一套 | 否 | 是（任务抽象） | — |
| 无 CI/基准/schema 版本 | 否 | 否 | **是** |
| 用户数据与回滚能力 | 否 | 否 | **是** |

> 结论：约 40% 的痛来自渲染栈，40% 来自分层与工程护栏，20% 来自计算执行层。重写只解决第一项，后两项必须平行推进，否则同样的债会搬到新架构。

### 3.4 现状运行时

```
┌──────────── 单一 Python 进程 ────────────────────────┐
│ Qt 事件循环 + 10 个 QWidget 页面（启动即全建）        │
│   绘制：QPainter 每帧重建对象                         │
│   富文本：每 60ms 全量 setHtml                        │
│   图片：主线程同步解码                                │
│ 30 个页面私有 QThread                                │
│ 计算：os.walk / hashlib / PIL / 纯 Python 余弦        │
│ 数据：sqlite3 每线程连接，每语句 commit                │
└──────────────────────────────────────────────────────┘
```

---

## 4. 目标架构设计【A】

### 4.1 进程与线程模型

```
┌─ Electron Main（Node / TypeScript）──────────────────────────┐
│ 窗口与原生能力：dialog / shell.openPath / 菜单 / 托盘 / 单实例 │
│ IPC 路由（ipcMain.handle）+ 参数校验 + 超时 + 错误封装        │
│ Python sidecar 管理：spawn / health / restart / 退出时杀进程树 │
│ 分页缓存（LRU，按 data_version 失效）                         │
│ 自定义协议：filenest-thumb://（缩略图字节流）                 │
└───────────────┬──────────────────────────────────────────────┘
                │ contextBridge（preload，白名单 API）
┌───────────────▼──────────────────────────────────────────────┐
│ Renderer（Chromium / Vue 3 + TypeScript）                     │
│ 视图：10 个页面 + 设计系统组件                                 │
│ 状态：reactive store（当前页/筛选/选中/主题）                  │
│ 虚拟滚动：固定行高 + 可视区渲染                                │
│ 流式对话：块级列表 + 仅更新最后一块                            │
└───────────────┬──────────────────────────────────────────────┘
                │ 回环 HTTP + token（127.0.0.1:随机端口）
┌───────────────▼──────────────────────────────────────────────┐
│ Python sidecar（无 Qt，FastAPI 复用 101 路由 + 新增 6 个）     │
│ 业务：规则/分类/去重策略/操作计划/生命周期/工作区              │
│ AI：多后端编排 / 流式 / embedding / 隐私控制                   │
│ 解析：PyMuPDF / python-docx / python-pptx / pytesseract / ffprobe│
│ 计算：ProcessPoolExecutor（扫描 / 哈希 / dHash / 向量）        │
│ 数据：SQLite 唯一写者（事务 / 迁移 / FTS5 / 回收区 / 撤销）     │
└──────────────────────────────────────────────────────────────┘
```

**线程与职责规则**

| 位置 | 允许 | 禁止 |
|------|------|------|
| Main | IPC 路由、缓存、进程管理、文件对话框 | 业务规则、SQL、长耗时计算 |
| Renderer | DOM、状态、虚拟滚动、轻量格式化 | 文件系统访问、Node API、长任务 |
| Sidecar | 全部业务与数据、IO、计算 | 任何 GUI 依赖 |

### 4.2 模块划分与职责边界

| 模块 | 位置 | 职责 | 边界（禁止事项） |
|------|------|------|------------------|
| Shell | 【A】`desktop/src/main/**` | 窗口/菜单/托盘/单实例/自动更新预留 | 不写业务判断 |
| Bridge | 【A】`desktop/src/preload/**` | 暴露白名单 API、类型定义 | 不暴露 `ipcRenderer` 原始对象 |
| IPC Gateway | 【A】`desktop/src/main/ipc/**` | 校验参数、超时、重试、错误归一 | 不缓存超过 3 页 |
| Page Cache | 【A】`desktop/src/main/cache/**` | LRU 分页缓存 + 版本失效 | 不持久化 |
| Thumb Proto | 【A】`desktop/src/main/protocol/**` | 缩略图字节流供给 | 不做图像编辑 |
| UI Kit | 【A】`desktop/src/renderer/components/**` | 按钮/输入/卡片/表格/弹窗/骨架 | 不含业务逻辑 |
| Pages | 【A】`desktop/src/renderer/pages/**` | 一页一目录，组合组件与 store | 不直接拼接口 URL |
| Stores | 【A】`desktop/src/renderer/stores/**` | 页面状态与筛选条件 | 不做数据转换业务 |
| Service App | `service/app.py` | FastAPI 入口、生命周期、鉴权 | 不含 Qt |
| Core | `service/core/**` | 扫描/分类/去重/AI/规则/文件操作 | 不 import PyQt6、不 import UI |
| Data | `service/database/**` | DAO、事务、迁移、FTS | 不写业务规则 |
| Tasks | `service/core/tasks.py` | 统一任务抽象（提交/取消/进度/异常） | 不依赖 Qt 信号 |
| Bench | `bench/` | 基线采集与回归 | 不进入发布产物 |

### 4.3 关键接口与数据流

#### 4.3.1 三层契约

| 层 | 机制 | 约定 |
|----|------|------|
| Renderer ↔ Main【A】 | `contextBridge` + `ipcRenderer.invoke` | 仅暴露 `window.api.*` 白名单；返回 `{ok, data}` 或 `{ok:false, code, message}` |
| Main ↔ Sidecar | HTTP/1.1 + JSON | `127.0.0.1` 随机端口 + 一次性 token（`X-Filenest-Token`）；超时 15s |
| Sidecar ↔ SQLite | `sqlite3`（线程局部连接） | 唯一写者；写操作走事务；只增列迁移 |
| 进度与事件 | SSE（`text/event-stream`） | `/api/events`：扫描进度、监控事件、任务状态、`data_version` |

#### 4.3.2 新增/复用端点

| 端点 | 状态 | 用途 |
|------|------|------|
| `GET /api/health` | 新增 | 版本、`schema_version`、`data_version`、pid |
| `GET /api/events` | 新增 | SSE 事件流（进度/监控/失效通知） |
| `POST /api/scan/start`、`POST /api/scan/cancel` | 新增 | 扫描由 UI 触发（原先只在 GUI 内） |
| `GET /api/thumb` | 新增 | 缩略图字节（Pillow，复用现有依赖） |
| `POST /api/shutdown` | 新增 | 优雅退出 |
| `GET /api/dashboard`、`/api/files`、`/api/content/search`、`/api/duplicates*`、`/api/tags*`、`/api/recycle` | 复用 | 现有 101 路由 |

#### 4.3.3 五条关键数据流

**① 列表分页**

```
Renderer（滚动到阈值）→ window.api.listFiles(cursor)
  → Main：命中页缓存？返回 : 请求 /api/files?cursor=…&limit=200
  → Sidecar：keyset 查询（WHERE (scan_time,id) < (?,?) ORDER BY … LIMIT 200）
  → 回填缓存 → 返回 {rows, nextCursor, dataVersion}
```

**② 扫描入库**

```
Renderer 点“开始扫描”→ Main → POST /api/scan/start
Sidecar：ProcessPoolExecutor 遍历+哈希 → 批量事务入库（2000 条/批）
        → 每 300ms 推 SSE 进度 → Main → Renderer 进度条
完成：data_version + 1 → Main 清缓存 → Renderer 刷新列表
```

**③ 文件操作（重命名/移动/删除）**

```
Renderer 弹出确认（影响范围/冲突/不可逆项）
  → Main（二次确认 + 路径校验）
  → POST /api/files/rename（不自动重试，防重复执行）
  → Sidecar：file_manager + operation_history（支持撤销）
  → 返回新 data_version → Renderer 局部更新 + 失效缓存
```

**④ AI 流式回答**

```
Renderer 输入 → Main → POST /api/ai/chat（SSE）
Sidecar：ai_layer 流式产出 → Main 转发 token
Renderer：按 Markdown 块切分追加 DOM，仅更新最后一块
代码块高亮：由 Sidecar 返回 HTML 片段（复用 Pygments）
```

**⑤ 缩略图**

```
Renderer <img src="filenest-thumb://…/path?size=256">
  → Main 协议处理器：内存缓存 → 磁盘缓存 → GET /api/thumb
  → Sidecar：Pillow 解码即缩放（不整图解码）→ 返回 WebP/PNG 字节
```

### 4.4 渲染与交互规范【A】

**设计 token（`renderer/styles/tokens.css`）**

| 类别 | 取值 |
|------|------|
| 色板 | 底 `#0f0f1a`、卡 `#1a1e2e`、描边 `#2a2f45`、主 `#3b82f6`、成功 `#10b981`、警告 `#f59e0b`、危险 `#ef4444`、主文 `#e8e8ef`、次文 `#a0a0b0` |
| 间距 | 4 / 8 / 12 / 16 / 24 / 32 |
| 圆角 | 6 / 8 / 12 / 16 |
| 字体 | 系统栈：`Microsoft YaHei UI` / `PingFang SC` / `Noto Sans CJK SC`；字号 11/12/13/15/20/26 |
| 动效 | 页面切换 180ms `cubic-bezier(.2,0,0,1)`；hover 80ms；Toast 220ms；骨架 shimmer 1.2s |
| 层级 | 卡片用底色 + 1px 描边，不用重投影 |

**关键实现约束**

| 场景 | 做法 | 禁止 |
|------|------|------|
| 大列表 | 固定行高虚拟滚动（自研，约 150 行），可视区 ±5 行 | 全量渲染 / 动态行高 |
| 表格 | CSS Grid + 虚拟滚动 | 引入重型表格库 |
| 图表 | ECharts（`echarts/core` 按需注册 + 动态 `import()` 懒加载）；主题变更时 `setOption` 更新而非重建实例 | 全量引入 `echarts`、每帧 `setOption`、实例不 `dispose` |
| 富文本 | `markdown-it`（`html:false`）→ `DOMPurify` 净化 → 块级数组追加；代码块由 sidecar 返回 HTML | 启用原始 HTML、未净化直接 `v-html`、每次全量重设 `innerHTML` |
| 图片 | `loading="lazy"` + `filenest-thumb://` 协议 + 固定尺寸占位 | 直接读本地文件路径 |
| 主题 | 切换 `data-theme` 属性 + CSS 变量 | 运行时拼接大段样式 |

### 4.5 安全模型【A】

| 面 | 措施 |
|----|------|
| 渲染进程 | `contextIsolation: true`、`nodeIntegration: false`、`sandbox: true` |
| 导航 | `will-navigate` 阻止外部跳转；`setWindowOpenHandler` 一律 deny |
| CSP | `default-src 'self'; img-src 'self' filenest-thumb: data:; connect-src 'none'`（渲染进程不直连网络） |
| 桥接 | 仅暴露方法，不暴露 `require`/`process`/`ipcRenderer` |
| Sidecar | 仅监听回环、随机端口、一次性 token、校验 `Host`/`Origin` 防 DNS rebinding |
| 文件操作 | 路径必须落在已配置扫描根目录内；破坏性操作二次确认；写操作不自动重试 |
| 外部链接 | 一律 `shell.openExternal` 且需用户确认 |

### 4.6 数据所有权与一致性

- **单写者**：仅 sidecar 写 SQLite；Main 只读缓存，不建连接。
- **版本号**：任何写操作递增 `data_version`；Main 与 Renderer 比对后失效缓存。
- **一致性边界**：列表页允许"最多落后一次写操作"，通过 SSE 通知即时纠正。
- **迁移**：启动时校验 `schema_version`，迁移前自动备份 `.db.bak-<version>`。

### 4.7 目录结构【A】

```
FileNest/
├── desktop/                       # Electron 应用
│   ├── package.json
│   ├── electron-builder.yml
│   ├── tsconfig.json
│   ├── vite.config.ts             # 仅构建 renderer
│   ├── scripts/build-main.mjs     # esbuild 构建 main/preload（随 Vite 提供，无新依赖）
│   ├── src/
│   │   ├── main/{index.ts,ipc/,cache/,protocol/,sidecar/}
│   │   ├── preload/{index.ts,api.d.ts}
│   │   └── renderer/{App.vue,components/,pages/,stores/,styles/}
│   └── resources/                 # 图标、静态资源
├── service/                       # 原 Python 工程（无 Qt）
│   ├── app.py                     # FastAPI 入口
│   ├── core/ database/ utils/
│   └── packaging/sidecar.spec
├── bench/                         # 基准与数据集
├── docs/                          # 本方案、ADR、性能报告
└── cli.py                         # 保留，直连 sidecar
```

---

## 5. 重大改动：理由与替代方案

> 本章对应约束"影响范围较大的改动需说明理由与替代方案"。

### 5.1 移除 PyQt6 全部界面

| 项 | 内容 |
|----|------|
| 改动 | 删除 `ui/` 16,825 行；发布物不再包含 PyQt6 |
| 理由 | ① 用户明确要求画面不经 Python；② PyQt6 为 GPLv3 与项目 MIT 冲突；③ QSS 内联 188 处导致主题切换重抛光 |
| 替代 | ① 保留 PyQt6 + QML 局部替换（被否决：仍含 Python 渲染进程）；② 保留 PyQt6 仅做优化（被否决：画面上限不变） |
| 回退 | v2.7 分支完整保留；数据向前兼容，可随时回装 |

### 5.2 引入 Electron 双进程【A】

| 项 | 内容 |
|----|------|
| 改动 | 新增 Electron 主进程 + 渲染进程 + preload 桥 |
| 理由 | ① 自带 Chromium，满足"解压即用"，不依赖系统 WebView；② 与已具备的 Vue/TS 技能匹配；③ 生态成熟、踩坑资料最多 |
| 替代 | Tauri（需 Rust，且体积优势依赖系统 WebView）、QML（需重学两门）、JavaFX（观感上限低） |
| 代价 | 安装包 +150~200MB、内存 +150~250MB（Chromium 固定成本），已写入 §2.3 体积预算 |
| 退出条件 | 若 P0 实测"包体超基线 2× 且无法通过裁剪解决"，回退到 Tauri 方案（此时 Vue 代码可 100% 复用，仅换壳） |

### 5.3 计算仍用 Python，不引入 Rust/Node 原生模块

| 项 | 内容 |
|----|------|
| 改动 | 扫描/哈希/dHash 保留 Python，改为 `ProcessPoolExecutor` 多进程 + 批量化；数值密集部分（向量、汉明、位打包）改由 **numpy** 向量化 |
| 理由 | ① 约束"不引入未确认新技术"；② `hashlib`/`Pillow` 底层已是 C，真正的瓶颈是 GIL 与逐项开销，多进程即可解决；③ 避免 JS/Python 两套遍历逻辑不一致；④ numpy 已具备，可把"Python 级循环"换成 BLAS/SIMD |
| 替代 | ① Node `worker_threads`（否决：需在 JS 重写遍历/哈希，双份逻辑）；② Rust + napi-rs（否决：新增语言与构建链）；③ Web Worker + WASM（否决：图像解码仍要回 Python）；④ scipy/pandas/faiss（否决：只用到其中一两个函数，体积与维护不划算） |
| numpy 分工 | **向量检索**：启动时把 `file_embeddings` 载入 `(N, D)` float32 矩阵（1 万×768 ≈ 30MB），写入时增量追加/删除，查询单次 `matmul` + `argpartition` 取 Top-K；**相似分组**：分块 XOR + popcount 计算汉明距离（每块 ≤ 512 行，避免 N² 内存）；**dHash**：`np.packbits` 替代 64 次 Python 循环（收益有限，主因是解码开销） |
| 不适用 | 目录遍历、哈希、文件 IO 仍是**多进程**而非 numpy：这些是 syscall/串行 IO 问题，向量化帮不上忙 |
| 验收 | 8 核机器上扫描 ≥ 2.5×、哈希 ≥ 2×、dHash ≥ 3×；1 万×768 语义检索 p95 ≤ 50ms；1 万张相似分组 ≤ 400ms |
| 说明 | 这是方案A相对 Rust 方案**唯一的能力让渡**：单文件大文件哈希仍受单核限制（多进程只能并行多文件） |

### 5.4 列表改为 keyset 分页 + 前端虚拟滚动【A】

| 项 | 内容 |
|----|------|
| 改动 | 后端 `OFFSET` → keyset；前端一次性只保留 3 页窗口 |
| 理由 | 深分页恒定耗时；虚拟滚动使 DOM 节点数恒定 |
| 替代 | ① 游标 + 无限滚动（否决：无法跳页）；② 前端全量加载（否决：10 万行内存不可控）；③ 引入重型表格库（否决：新增依赖且收益有限） |

### 5.5 图表采用 ECharts（按需引入）【A】

| 项 | 内容 |
|----|------|
| 改动 | 饼图/柱图/折线图由 ECharts 渲染，替代"移植 QPainter 逻辑自绘 SVG" |
| 理由 | ① 交互（tooltip、图例切换、缩放）开箱即用，自绘需数百行；② 轴标签避让、CJK 排版、响应式 resize 由库处理；③ 已掌握，边际学习成本为零；④ 后续目录画像/趋势图需求增长时无需二次迁移 |
| 替代 | ① 自绘 SVG（否决：交互与边界处理成本高，收益仅在体积）；② Chart.js（否决：同类能力但中文生态与文档弱于 ECharts） |
| 体积控制 | 仅注册 `PieChart`/`BarChart`/`LineChart` + `GridComponent`/`TooltipComponent`/`LegendComponent` + `CanvasRenderer`；按需引入约 150–250KB（gzip，P2 实测）；**必须动态 `import()`，不进入首屏包** |
| 渲染器 | 默认 Canvas（大数据量更稳）；仅在需要 CSS 动画/无障碍时评估 SVG 渲染器 |
| 生命周期 | `onMounted` 创建实例、`onBeforeUnmount` `dispose()`；`ResizeObserver` 触发 `resize()`；主题切换用 `setOption` 增量更新而非重建 |
| 约束 | 由 §10.1"首屏 JS"指标与 §10.3 CI 门禁守住体积，不以"能跑"为交付标准 |

### 5.6 Markdown 引入 markdown-it + DOMPurify【A】

| 项 | 内容 |
|----|------|
| 改动 | 用 `markdown-it` 解析 + `DOMPurify` 净化，替代"移植现有正则渲染器" |
| 理由 | ① **正确性**：嵌套列表、表格对齐、引用块、行内代码与强调混排、CJK 标点邻接，正则链难以覆盖；② **安全**：渲染进程持有 `window.api` 桥，XSS 等价于本地文件操作权限，成熟库 + 净化器的防护面远小于自写正则（如 `javascript:` 协议、属性注入）；③ **性能**：解析 5k 字约 1–2ms，且可只解析末尾块；④ **可维护**：边缘 case 由社区修复 |
| 替代 | ① 移植现有正则渲染器（否决：需自补安全校验与规范覆盖）；② `marked`（可用，但插件生态弱）；③ 由 sidecar 渲染整段 HTML（否决：流式时每次都要跨进程往返） |
| 安全配置 | `html: false`、`linkify: false`、`breaks: false`；链接协议白名单（`http`/`https`/`mailto`/内部 `cite:`）；渲染后 `DOMPurify.sanitize()` 并限定 `ALLOWED_TAGS/ALLOWED_ATTR`；外链统一 `shell.openExternal` |
| 流式策略 | 按空行/代码围栏切块，仅重解析并替换最后一块；代码块闭合后才触发高亮 |
| 代码高亮 | 仍由 sidecar 的 Pygments 生成 HTML（复用现有主题与依赖）；不引入 shiki/highlight.js（体积 1MB+ 且需维护双份主题） |
| 体积 | markdown-it ≈ 35KB（gzip）+ DOMPurify ≈ 20KB（gzip），可进首屏包 |
| 行为差异 | 生成的标签结构与本项目样式不同，P2 设计系统统一 `.md-*` 样式类，并纳入视觉回归 |

### 5.7 安全模型收紧

| 项 | 内容 |
|----|------|
| 改动 | 渲染进程 sandbox + CSP + 白名单桥 + Host/Origin 校验 |
| 理由 | 本地文件操作接口一旦被渲染进程或外部网页触达，等价于"任意文件删除"漏洞 |
| 替代 | 关闭 sandbox 换取开发便利（否决：不可接受） |

---

## 6. 分阶段实施步骤与验收标准

### 6.1 里程碑

| 阶段 | 周期 | 主题 | 里程碑 | 退出准则 |
|------|------|------|--------|----------|
| P0 | 1.5 周 | 度量与骨架 | M0 | 基线入库；Electron 空壳 + sidecar 握手跑通；打包可运行 |
| P1 | 3 周 | 服务化与数据治理 | M1 | Python 无 Qt 全量测试通过；数据层指标达标；并行计算达标 |
| P2 | 3 周 | 渲染骨架与设计系统 | M2 | 设计系统 Demo + 仪表盘功能对等；帧时达标 |
| P3 | 6 周 | 页面迁移 | M3 | 9 个页面功能对等；快捷键全通；视觉回归通过 |
| P4 | 2.5 周 | 收尾与发布 | M4 | 全指标达标；灰度通过；回滚演练通过 |

```
周次   1   2   3   4   5   6   7   8   9  10  11  12  13  14  15  16  17
P0    ███
P1        ██████████
P2                  ██████████        （W5–W7，与 P1 重叠 1 周）
P3                              ██████████████████
P4                                                ████████
```

### 6.2 P0：度量与骨架（1.5 周）

| 任务 | 优先级 | 产出 |
|------|--------|------|
| T0-1 基准套件（启动/首帧/切换/滚动/主题/扫描/哈希/dHash/检索/内存） | P0 | `bench/run_all.py` + JSON |
| T0-2 合成数据集（1k/1 万/10 万，固定种子） | P0 | `bench/gen_dataset.py` |
| T0-3 采集现有 PyQt6 版本基线 | P0 | `docs/perf/BASELINE.md` |
| T0-4 Electron 空壳（窗口/首帧/sidecar 启动） | P0 | `desktop/` 骨架 |
| T0-5 sidecar 握手（health/token/优雅退出/杀进程树） | P0 | 启动器 + 冒烟脚本 |
| T0-6 打包链（electron-builder + PyInstaller onedir） | P1 | 可安装产物 |
| T0-7 许可证确认（移除 PyQt6） | P1 | ADR-001 |

**验收**：空壳首帧 ≤ 400ms；sidecar 就绪 ≤ 1.2s；同机两次基准偏差 ≤ 10%；安装包在干净 Win11 虚拟机可运行。

### 6.3 P1：服务化与数据治理（3 周）

| 任务 | 优先级 | 验收 |
|------|--------|------|
| T1-1 `core/` 去 Qt（`QThread` → `tasks.py` 抽象；信号 → 回调/队列） | P0 | `python -c "import core"` 无 PyQt6；`pytest` 全绿 |
| T1-2 `app.py` 统一入口（app_version/schema_version/data_version、token、优雅退出） | P0 | 健康检查与退出流程通过 |
| T1-3 新增 6 个端点（health/events/scan/thumb/shutdown） | P0 | 契约测试通过 |
| T1-4 DB 事务上下文 + 批量写 + keyset 分页 + 列裁剪 + 复合索引 | P0 | 批量写 ≥ 3×（应用层含 FTS 触发器，实测口径见 BASELINE §2）；深分页耗时 ≈ 首屏 |
| T1-5 统一任务抽象（进度/取消/超时/异常，支持进程池） | P0 | 取消后 1s 内停止；无悬挂 |
| T1-6 计算多进程化（扫描/哈希/dHash）+ 批量化入库 | P0 | 扫描 ≥ 2.5×、哈希 ≥ 2×、dHash ≥ 3× |
| T1-7 numpy 向量检索（矩阵缓存 + 写入增量更新 + 预归一化 + `matmul`/`argpartition`） | P0 | p95 ≤ 50ms（1 万×768）；矩阵缓存 ≤ 64MB |
| T1-10 numpy 相似分组（分块 XOR + popcount，替代 O(n²) 纯 Python 比较） | P1 | 1 万张 ≤ 400ms；结果与纯 Python 实现一致 |
| T1-8 修复跨线程共享连接 | P0 | 并发 100 次无锁错误 |
| T1-9 结构化日志（进程标签）+ 性能埋点 | P1 | `perf.log` 可解析 |

**验收**：无 Qt 环境跑通 31 个测试 + 新增契约测试；G3 全部达标；`cli.py`/HTTP 契约不变。

### 6.4 P2：渲染骨架与设计系统【A】（3 周）

| 任务 | 优先级 | 验收 |
|------|--------|------|
| T2-1 Main 骨架（窗口/菜单/托盘/单实例/窗口状态持久化） | P0 | 冷启动可交互 ≤ 1.5s |
| T2-2 IPC 网关（typed API、超时、重试、错误归一） | P0 | 错误可展示且不崩溃 |
| T2-3 Sidecar 管理（spawn/health/restart/kill-tree） | P0 | 注入崩溃 20 次全部恢复；无孤儿进程 |
| T2-4 页缓存（LRU + data_version 失效） | P1 | 滚动期间 IPC 命中率 ≥ 70% |
| T2-5 设计系统（token + 12 个基础组件 + Demo 页） | P0 | 视觉评审通过 |
| T2-6 虚拟滚动容器 + 表格组件 | P0 | 10 万行 p95 ≤ 16.7ms |
| T2-7 仪表盘页（统计卡/活动/趋势/待处理） | P0 | 功能对等 |
| T2-8 主题切换/Toast/命令面板/全局快捷键 | P0 | 快捷键全通 |
| T2-9 ECharts 封装（按需注册 + 动态 import + 主题联动 + resize/dispose） | P0 | 图表区 60fps；首屏 JS ≤ 300KB(gzip) |
| T2-10 Markdown 模块（markdown-it + DOMPurify + 块级切分 + `.md-*` 样式） | P1 | 5k 字渲染 ≤ 5ms；XSS 用例全部拦下 |

**验收**：M2 演示可完整操作仪表盘；主题切换 ≤ 120ms；无 `nodeIntegration` 泄漏；图表与 Markdown 模块单测覆盖安全用例。

### 6.5 P3：页面迁移【A】（6 周）

| 批次 | 页面 | 关键点 |
|------|------|--------|
| 3.1（3 周） | 分类管理、文件搜索 | 虚拟表格、右键菜单、预览面板（图片/代码/PDF 首页）、CSV 导出 |
| 3.2（3 周） | AI 对话、扫描管理、重复文件 | 块级流式、引用锚点、任务进度与取消、多阶段检测进度 |
| 3.3（并行） | 回收区、操作历史、标签管理、系统设置 | 表单与列表复用组件；AI 设置与隐私控制台 |

**验收**：功能对等清单 100%（§附录B）；视觉回归 diff 通过；soak 4 小时内存无增长。

### 6.6 P4：收尾与发布（2.5 周）

| 任务 | 产出 |
|------|------|
| T4-1 删除 PyQt6 残留与 `requirements.txt` 清理 | 依赖清单 |
| T4-2 打包/签名/体积校验 | 安装包 |
| T4-3 文档（架构/升级/回滚/维护） | `docs/` |
| T4-4 灰度（内部 3 人 → 10 人 → 公开） | 灰度记录 |
| T4-5 回滚演练（页面级/服务级/版本级/数据级） | `docs/perf/ROLLBACK_DRILL.md` |

**验收**：M4 全部指标达标；演练 4 级全部通过。

---

# 第二部分：实施方案

## 7. 执行计划

### 7.1 任务拆解与优先级（按模块汇总）

| 模块 | 任务数 | 人日（估） | 优先级分布 |
|------|--------|-----------|-----------|
| 基准与工具链 | 7 | 12 | P0×5, P1×2 |
| Python 服务化 | 9 | 28 | P0×7, P1×2 |
| 数据层 | 5 | 15 | P0×4, P1×1 |
| 计算并行化与 numpy 向量化 | 5 | 15 | P0×4, P1×1 |
| Electron 壳与 IPC | 8 | 24 | P0×5, P1×3 |
| 设计系统 | 6 | 18 | P0×4, P1×2 |
| 图表与 Markdown 模块（ECharts / markdown-it + DOMPurify） | 2 | 9 | P0×1, P1×1 |
| 页面迁移（9 页） | 18 | 50 | P0×12, P1×5, P2×1 |
| 打包/发布/文档 | 6 | 12 | P0×2, P1×4 |
| **合计** | **66** | **约 183 人日** | — |

> 单人执行约 37 周（含缓冲），双人并行约 17–18 周（与 §6 一致）。图表与 Markdown 引入库后，页面迁移内部自绘工作量相应减少（52 → 50 人日）；numpy 向量化增加约 3 人日（矩阵缓存与增量维护）。

### 7.2 时间节点（示例日历，T0 = 2026-11-24）

| 里程碑 | 周次 | 日期 | 交付物 |
|--------|------|------|--------|
| T0 启动 | W1 | 2026-11-24 | 环境与基准开工 |
| M0 | W2 末 | 2026-12-04 | 基线报告 + 空壳 + 打包 PoC |
| M1 | W5 末 | 2026-12-25 | 无 Qt 服务 + 数据层 + 并行计算 |
| M2 | W8 末 | 2027-01-15 | 设计系统 + 仪表盘 |
| M3 | W14 末 | 2027-02-26 | 9 页迁移完成 |
| M4 | W17 末 | 2027-03-19 | 发布 v3.0 |

> 2027 年春节（2 月 6 日前后）落在 P3 末段，已在 W13–W14 预留 3 天缓冲。

### 7.3 人员分工

| 角色 | 投入 | 负责 | 交付 |
|------|------|------|------|
| 开发 A（后端/架构） | 100% | P0 基准、P1 服务化与数据层、IPC 契约、打包 | M0/M1 及 P4 发布 |
| 开发 B（前端） | 100% | P2 壳与设计系统、P3 页面迁移 | M2/M3 |
| 开发 A + B | 交叉 | 缩略图链路、AI 流式、视觉回归 | — |
| 测试/发布（兼职） | 40% | 基准、对拍、soak、灰度、回滚演练 | 各阶段验收报告 |

单人执行时按 P0 → P1 → P2 → P3 → P4 串行，前端任务优先级降一档，先做"能跑通的最小页面"。

### 7.4 测试与回归策略

| 层 | 内容 | 工具 | 门禁 |
|----|------|------|------|
| 单元 | 现有 31 个测试 + 新增任务/事务/契约测试 | pytest | 必须 |
| 契约 | 101 路由的请求/响应快照；CLI 输出结构 | pytest | 必须 |
| 集成 | 扫描→分类→去重→索引→清理 端到端 | pytest（slow） | 必须 |
| IPC | Main ↔ Sidecar 超时/重试/错误码 | 冒烟脚本 | 必须 |
| UI 冒烟 | 用 Electron `executeJavaScript` 驱动关键路径 + `capturePage` 截图 | 自建 harness（无新依赖） | 必须 |
| 视觉回归 | 固定尺寸截图 + 逐像素 diff（容差） | Python + Pillow（复用） | 无结构性差异 |
| 性能 | §10 指标 | `bench/` | 回退 > 5% 失败 |
| 稳定性 | 8 小时连续扫描/索引/预览 | soak 脚本 | 内存无单调增长 |
| 兼容 | 旧库打开、旧配置导入、v2.7 读新库 | pytest | 必须 |

### 7.5 上线与灰度

| 阶段 | 范围 | 观察期 | 通过标准 |
|------|------|--------|----------|
| 内部 | 3 名维护者 | 1 周 | 无 P1 缺陷；CPU/内存正常 |
| 小范围 | 10 名用户（含大数据集） | 1 周 | 崩溃率不升；指标达标；sidecar 崩溃 ≤ 1 次 |
| 公开 | v3.0 | 2 周 | 无回滚触发 |

**发布检查清单**：功能对等清单全绿；性能指标达标；签名有效；体积达标；干净虚拟机安装通过；回滚包可下载；升级说明已发。

### 7.6 回滚预案

| 级别 | 触发条件 | 操作 | 耗时 | 数据影响 |
|------|----------|------|------|----------|
| R1 页面级 | 单页缺陷 | 关闭该页入口（配置开关）或回退该页组件版本 | < 1 分钟 | 无 |
| R2 服务级 | sidecar 反复崩溃 | 重启；或 `--safe-mode`（禁用 AI/索引）启动 | < 1 分钟 | 无 |
| R3 版本级 | 崩溃率上升/指标未达标/数据异常 | 回装 v2.7（库只增列，可直读） | < 10 分钟 | 无 |
| R4 数据级 | 迁移损坏 | 停应用 → 恢复 `.db.bak-<version>` → 回装旧版 | < 15 分钟 | 回退到迁移前快照 |

**演练**：P2、P3 末各演练 R1/R2；P4 演练 R3/R4 并留存记录。

### 7.7 监控与后续维护

| 项 | 方案 |
|----|------|
| 日志 | `logs/app.log`（业务）+ `logs/perf.log`（埋点），两者都带进程标签；单文件 10MB 轮转 |
| 性能 | 启动分阶段打点、帧时采样（rAF）、IPC p50/p95、缓存命中率；设置页可查看 |
| 崩溃 | Electron `crashReporter` **默认关闭**，需用户显式同意；本地保留最近 3 份崩溃转储 |
| 诊断面板 | 版本、sidecar 状态、DB 大小/`schema_version`、缓存体积、最近错误 |
| 依赖维护 | 每季度一个升级窗口；升级前跑基准与契约测试 |
| 版本策略 | 语义化版本；`schema_version` 独立演进；每版保留 2 个历史安装包 |
| 技术债看板 | 未达标的指标（如向量检索）登记为债，按季度评估 |

---

## 8. 兼容性策略

| 维度 | 策略 |
|------|------|
| 数据库 | 只增列/加索引；新增 `schema_version` 表；迁移幂等；迁移前自动备份 |
| 哈希 | 新增 `hash_algo` 列（`sha256` 默认），混算期间按 `(hash_algo, file_hash)` 分组 |
| 用户配置 | 现有 `QSettings`（Windows 注册表 `HKCU\Software\FileNest\FileNest`）由 sidecar 一次性导出为 `config.json`；失败则回落默认值并记日志 |
| 回收区 | `.trash/` 结构不变，v2.7 可恢复 v3.0 删除的文件 |
| CLI | 参数与 JSON 输出不变，仅允许追加字段 |
| HTTP | 路径与字段不变；新增端点不影响旧客户端 |
| 快捷键 | 与现版一致（Ctrl+F / Ctrl+Shift+F / Ctrl+Shift+P / Ctrl+Z / Ctrl+R / F5 / Delete / F2） |
| 用户可见变化 | 仅允许"更快、更顺滑"与设置页新增"诊断信息"；功能语义零变更 |

---

## 9. 风险控制

| # | 风险 | 概率 | 影响 | 等级 | 缓解 | 触发与应对 |
|---|------|------|------|------|------|-----------|
| R1 | Vue 重写 16.8k 行 UI 超期 | 高 | 高 | 🔴 | 组件基座先行、一次一页、每页 Gate | P3 过半仍缺 3 页 → 缩减首版（低价值页延后）并明确告知 |
| R2 | Electron 体积/内存超预算 | 中高 | 中 | 🟠 | 裁剪非必需模块、按需加载页面、关闭无用特性 | 超基线 2× 且无法裁剪 → 触发 §5.2 退出条件（换壳，Vue 代码复用） |
| R3 | sidecar 生命周期问题（孤儿/重复启动/崩溃循环） | 中 | 高 | 🟠 | 单实例锁、退出杀进程树、崩溃计数上限、只读降级 | 出现孤儿进程 → 立即回退该版本 |
| R4 | 去 Qt 化遗漏隐藏依赖 | 中 | 中 | 🟡 | CI 在无 PyQt6 环境跑全量测试 | 暴露依赖 → 抽 `tasks.py` 抽象层逐处替换 |
| R5 | 多进程计算在 Windows 上的启动/序列化开销抵消收益 | 中 | 中 | 🟡 | 进程池复用、批量提交（≥500 文件/任务）、避免传大对象 | 未达 1.5× → 缩小任务粒度、改共享内存或标记为债 |
| R6 | 虚拟滚动/富文本出现白屏或跳动 | 中 | 中 | 🟡 | 固定行高、占位骨架、可视区 ±5 行预渲染 | 出现白屏 → 提高预取行数或降级为分页表格 |
| R7 | 安全模型配置错误导致本地接口被滥用 | 低 | 极高 | 🔴 | sandbox + CSP + 白名单桥 + Host/Origin 校验 + 路径校验 | 发现绕过 → 立即发补丁并关闭远程通道 |
| R8 | 用户习惯变化导致体验退化 | 中 | 中 | 🟡 | 布局与快捷键对齐现版；10 人试用 | 反馈集中 → 优先修交互 |
| R9 | 性能指标未达（尤其向量检索） | 中 | 中 | 🟡 | 已用 numpy 矩阵化 + 预归一化；未达标则调优分块大小与缓存策略 | 两阶段未达标 → 登记技术债，不阻塞发布 |
| R10 | 数据库迁移损坏 | 低 | 极高 | 🔴 | 只增列 + 备份 + 幂等 + 演练 | 失败 → 自动恢复 `.bak` 并阻止升级 |
| R11 | 前端依赖（ECharts / markdown-it / DOMPurify）漏洞或破坏性升级 | 中 | 中 | 🟡 | 锁定版本 + 季度审计 + CSP 与净化器兜底 | 出现高危公告 → 48h 内升级并回归视觉与安全用例 |

### 9.1 降级设计

| 层级 | 机制 | 恢复 |
|------|------|------|
| L1 sidecar 崩溃 | 界面提示 + 自动重启（≤2 次）+ 只读缓存浏览 | 自动/手动 |
| L2 请求超时 | 该区域显示错误态，不影响其他页 | 重试按钮 |
| L3 缩略图失败 | 占位图，不阻塞列表 | 后台重试 |
| L4 计算失败 | 退回单进程实现（保留原代码路径） | 重启后切回 |

---

## 10. 验收与度量

### 10.1 指标字典

> 已采集的实测基线（2026-11-18，Windows 11 / 12 核 / Python 3.14.9）见 `docs/perf/BASELINE.md`，原始数据 `bench/results/baseline-1k.json`。

| 类别 | 指标 | 采集 | 基线 | 目标 |
|------|------|------|------|------|
| 启动 | 首帧 | 进程启动 → 首次 `ready-to-show` 上屏 | P0 实测 | ≤ 400ms |
| 启动 | 可交互 | 点击有响应且首页数据可见 | P0 实测 | ≤ 1.5s |
| 启动 | sidecar 就绪 | 拉起 → `/api/health` 200 | P0 实测 | ≤ 1.2s |
| 交互 | 页面切换 | 点击导航 → 目标页可见 | P0 实测 | ≤ 100ms |
| 交互 | 列表滚动 p95 | 10 万条，2s 自动滚动 | P0 实测 | ≤ 16.7ms |
| 交互 | 主题切换 | 点击 → 重绘完成 | P0 实测 | ≤ 120ms |
| 交互 | 大图预览首像素 | 点击 → 出现 | P0 实测 | ≤ 150ms |
| IPC | 分页请求 p95 | 200 行往返 | P0 实测 | ≤ 20ms |
| IPC | 缓存命中率 | 滚动期间 IPC 次数 / 滚动行数 | — | ≥ 70% |
| 计算 | 扫描吞吐 | 10 万文件固定集 | P0 实测 | ≥ 2.5× |
| 计算 | 哈希吞吐 | 1GB 混合文件 | P0 实测 | ≥ 2× |
| 计算 | dHash | 5,000 张 4MP | P0 实测 | ≥ 3× |
| 计算 | 相似分组（1 万张） | 端到端（numpy 分块汉明） | P0 实测 | ≤ 400ms |
| 计算 | 语义检索 p95 | 1 万×768（矩阵缓存 + matmul） | P0 实测 | ≤ 50ms |
| 资源 | 内存（空库/10 万） | 稳定后采样 | P0 实测 | ≤ 基线 × 1.4 |
| 资源 | 安装包 | 打包产物 | 未压缩 539MB（BASELINE §3.1） | ≤ 300MB |
| 资源 | 首屏 JS（gzip） | `vite build` 产物统计 | — | ≤ 300KB；ECharts 不出现在首屏 chunk |
| 稳定 | sidecar 崩溃恢复 | 注入 20 次 | — | 100% 恢复 |
| 稳定 | 孤儿进程 | 强杀界面后检查 | — | 0 |
| 工程 | 单文件行数 | 静态检查 | 2,306 | ≤ 500 |
| 工程 | `QThread` / 内联样式 | 静态检查 | 30 / 188 | 0 / 0 |

### 10.2 基准方法

1. 固定机器、电源计划、关闭实时杀毒（记录偏差）、固定 Node/Python/Electron 版本。
2. 固定数据集（`--seed 42`），图片集单独生成。
3. 每项 warmup 1 次、采样 ≥ 10 次，报 p50/p95/max；记录环境三元组。
4. `bench/run_all.py --baseline --candidate` 输出差值表，JSON 入库便于 diff。
5. 以用户可感知指标为主（首帧、切换、滚动、点击到可见）。

### 10.3 CI 门禁

| 预算 | 阈值 | 执行 |
|------|------|------|
| 渲染进程长任务 | ≤ 16ms | 埋点告警（开发构建） |
| IPC 单次 | ≤ 20ms p95 | CI 基准 |
| 帧时回归 | p95 回退 > 5% 失败 | CI（P2 起） |
| 包体 | 超出预算失败 | CI（P0 起） |
| 首屏 JS | > 300KB(gzip) 或 ECharts 进入首屏 chunk 即失败 | CI（P2 起） |
| 单文件行数 | > 500 失败 | 静态检查 |

---

## 附录 A：关键证据索引

| 结论 | 位置 |
|------|------|
| 10 个页面启动即构造 | `ui/main_window.py:294-314` |
| 主题切换全树重设样式 | `ui/main_window.py:191,201-209` |
| 图表每帧新建绘制对象 | `ui/chart_widgets.py:146,164,212,240` |
| AI 回答全量重渲染 | `ui/ai_chat_page.py:256-269` |
| Markdown 正则链每帧执行 | `ui/ai_chat_page.py:591-616` |
| 主线程同步解码原图 | `ui/classify_tab.py:1541-1552` |
| 每页 500 行全量重置模型 | `ui/classify_tab.py:183-189,305` |
| 每语句提交 | `database/db_manager.py:68-96` |
| OFFSET 分页 + `SELECT *` | `database/models.py:80-87` |
| 全表载入后切片 | `core/content_indexer.py:55` |
| dHash Python 位循环 | `core/image_similarity.py:16-32` |
| 相似分组 O(n²) | `core/image_similarity.py:102-109` |
| 纯 Python 余弦 + 逐条解包 | `core/embedding_service.py:39-48,216-224` |
| 跨线程共享连接 | `core/embedding_service.py:80` |
| 去重 N+1 + 逐行写回 | `core/multistage_dedup.py:73-85,136-151` |
| 每文件两次 syscall | `core/file_scanner.py:45-58,159-173` |
| 业务层可无头运行 | `server.py:60-77` |
| 任务框架仅登记状态 | `core/task_manager.py:1-5` |

## 附录 B：功能对等清单

| 页面 | 必须保留 |
|------|----------|
| 仪表盘 | 4 统计卡、待处理入口、AI 洞察、类型饼图、活动列表、增长趋势、目录画像、快捷操作 |
| 扫描管理 | 目录选择/移除、递归与哈希选项、进度与 ETA、取消、任务中心、索引检查、清理中心、归档工具 |
| 分类管理 | 分类树、分页列表、筛选、预览（图片/代码/文本/PDF/DOCX）、右键菜单（打开/定位/复制/重命名/删除/永久删除/AI 描述）、整理规则管理 |
| 文件搜索 | 自然语言解析、多条件、FTS5、正文检索、分页、CSV 导出、智能集合、AI 结果回填 |
| AI 对话 | 多轮、流式、工具卡片、引用溯源、语义模式、模型切换、导出 Markdown、重试/重生成 |
| 重复文件 | 多阶段检测、分组分页、单副本删除、保留最新、AI 选择、相似图片、版本关系 |
| 回收区 | 恢复、永久删除、清空、分页 |
| 操作历史 | 三种视图、目录筛选、单条/批量撤销 |
| 标签管理 | 标签云、层级与别名、颜色、批量打标、分页 |
| 系统设置 | 通用/扫描/重命名/去重/AI 模型/隐私控制/工作区 |

## 附录 C：新增端点草案

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | `{app_version, schema_version, data_version, pid}` |
| GET | `/api/events` | SSE：`progress` / `watch` / `task` / `invalidate` |
| POST | `/api/scan/start` | `{path, recursive, compute_hash, ...}` → `{task_id}` |
| POST | `/api/scan/cancel` | `{task_id}` |
| GET | `/api/thumb` | `?path=&size=` → 图片字节 |
| POST | `/api/shutdown` | 优雅退出（仅回环 + token） |

## 附录 D：ADR 清单

1. ADR-001 采用 Electron + Vue3 + TS（含对 Tauri/QML/JavaFX 的否决）
2. ADR-002 Python 保留为 sidecar（单写者）
3. ADR-003 计算多进程化，不引入 Rust/Node 原生模块
4. ADR-004 列表 keyset 分页 + 前端虚拟滚动
5. ADR-005 图表采用 ECharts（按需注册 + 懒加载 + 主题联动）
6. ADR-006 Markdown 采用 markdown-it + DOMPurify（`html:false` + 协议白名单）
7. ADR-007 Electron 安全基线（sandbox/contextIsolation/CSP）
8. ADR-008 打包为 onedir sidecar + electron-builder
9. ADR-009 许可证：移除 PyQt6，采用 MIT/Apache 生态
10. ADR-010 指标与 CI 门禁
11. ADR-011 富文本块级追加 + 代码高亮留在 sidecar（Pygments）
12. ADR-012 数值计算采用 numpy（矩阵缓存 / 分块汉明 / 位打包），不接管 IO 与多进程
13. ADR-013 体积预算调整为 ≤300MB 安装包（接受 Electron 运行时成本）

## 附录 E：术语

| 术语 | 含义 |
|------|------|
| sidecar | 随主程序分发并由其管理的本地子进程 |
| 单写者 | 仅一个进程写数据库，其他只读/经其代理 |
| keyset 分页 | 基于排序键游标的分页，避免深 OFFSET |
| 虚拟滚动 | 只渲染可视区 DOM，节点数恒定 |
| 帧时 p95 | 95% 的帧耗时不超过该值 |
| 熔断 | 某调用连续失败后暂停并回退降级路径 |
