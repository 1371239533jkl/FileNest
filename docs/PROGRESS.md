# 项目进度

> 最后更新：2026-11-20　当前阶段：**P2 完成 / P3 待开始**　总体完成度：约 75%
> 方案与验收标准见 `docs/REFACTOR_PLAN.md`；性能基线见 `docs/perf/BASELINE.md`。

## 一句话现状

P0 全部走完（度量、骨架、sidecar 握手、打包，含一次体积决策）；P1 只做了数据层，计算与服务化未动。

## 里程碑

| 阶段 | 状态 | 完成度 | 说明 |
|------|------|--------|------|
| P0 度量与骨架 | ✅ 完成 | 100% | NSIS 安装包未产出（网络阻塞），其余达成 |
| P1 服务化与数据治理 | 🟡 收尾 | 约 85% | 数据层 + 计算内核 + 扫描服务 + 任务/SSE + 缩略图/退出/token 已落地；剩 watcher 等按需项 |
| P2 渲染骨架与设计系统 | ✅ 完成 | 100% | 7 个页面 + 组件库 + 截图回归 |
| P3 页面迁移 | ⬜ 未开始 | 0% | 依赖 P2 |
| P4 收尾与发布 | ⬜ 未开始 | 0% | — |

## 已完成（可验收）

| 编号 | 内容 | 证据 | 验收 |
|------|------|------|------|
| T0-1 | 基准套件（扫描/哈希/余弦/分组/SQLite/分页 + 自检） | `bench/run_all.py`、`--selftest` | 通过 |
| T0-2 | 固定种子数据集生成器 | `bench/gen_dataset.py` | 1,100 文件 / 85.1MB / seed 42 |
| T0-3 | 基线采集与报告 | `docs/perf/BASELINE.md`、`bench/results/baseline-1k.json` | 已入库（含一次口径修正） |
| T0-4 | Electron + Vue 3 + TS 骨架 | `desktop/` | `npm run build` 通过 |
| T0-5 | sidecar 握手（随机端口 / health / 杀进程树） | `desktop/src/main/sidecar.ts` | `npm run smoke` → PASS，无孤儿进程 |
| T0-6 | 打包链路（PyInstaller onedir + electron-builder） | `desktop/packaging/build-sidecar.cmd`、`package.json` | 未压缩 539MB；`FileNest.exe --smoke` 退出码 0 |
| — | 体积决策：接受 Electron 成本，预算改 ≤300MB | ADR-013 | 已确认 |
| T1-4a | DB 事务上下文 + keyset 分页 + 复合索引 | `database/db_manager.py`、`models.py` | 4 个测试通过、冒烟通过 |
| T1-6 | 计算内核：单次 stat 遍历 + 多进程哈希 | `core/scan_engine.py`、`bench/run_compute.py` | 遍历 1.64×、哈希冷盘 14.2×/热缓存 2.2×，9 个测试通过 |
| T1-1a | 扫描入库服务去 Qt 并接入服务端 | `core/scan_service.py`、`server.py` | 端到端 6.15s → 1.35s（4.6×）；`/api/scan` 1,100 文件 76ms |
| T1-2a | 后台任务 + SSE 进度（`scan/start`、`scan/cancel`、`tasks`、`events`） | `core/task_runner.py`、`server.py` | 22k 文件：18 帧进度、5.06s、22000 条全部入库 |
| T1-2b | 缩略图、优雅退出、请求 token | `server.py`、`desktop/src/main/sidecar.ts` | `/api/thumb` 返回 JPEG；`/api/shutdown` 退出干净；无 token 401；冒烟 PASS 且 0 残留进程 |
| T2-1 | 渲染层 → preload → 主进程 → API 链路 | `desktop/src/main/api.ts`、`preload/index.ts` | 路径白名单 + token；渲染层无直连网络（CSP `connect-src 'none'`） |
| T2-2 | 设计 token + 基础组件 + 仪表盘 | `renderer/styles`、`components`、`pages/DashboardPage.vue` | 1100 文件真实数据渲染，截图见 `docs/screenshot_v3_dashboard.png` |
| T2-3 | 文件表格：虚拟滚动 + keyset 分页 + 右键菜单 | `renderer/pages/FilesPage.vue`、`web_api.py` | 2.2 万行滚动 p95 5.8ms/max 6.4ms；分页不重不漏（测试覆盖）；截图 `docs/screenshot_v3_files.png` |
| T2-4 | 抽出 DataTable / AppButton + 组件总览页 | `components/DataTable.vue`、`pages/Styleguide.vue` | 表格三种状态可预览；重构后性能复测 p95 6.2ms；截图 `docs/screenshot_v3_styleguide.png` |
| T2-5 | 预览面板：图片缩略图 + 文本头部 + 元信息 | `main/api.ts`、`main/files.ts`、`pages/FilesPage.vue` | 图片经 `/api/thumb` 返回 data URI；文本限 8KB 且仅白名单扩展名；截图 `docs/screenshot_v3_preview.png` |
| T2-6 | 多条件筛选：名称/正文/类型/大小区间/日期区间 | `pages/FilesPage.vue`、`tests/test_api_tasks.py` | 名称走 FTS 前缀、大小/类型走条件查询；测试覆盖三种筛选；截图 `docs/screenshot_v3_search.png` |
| T2-7 | 扫描页：目录选择 + 后台任务 + 进度 + 取消 | `pages/ScanPage.vue`、`main/api.ts` | UI 触发实测 22,000 文件：64% / 14201 条 / 2.1s，进度条随轮询更新；截图 `docs/screenshot_v3_scan.png` |
| T2-8 | 重复文件页：分组列表 + 保留选择 + 确认清理 | `pages/DuplicatesPage.vue`、`web_api.py` | 修复 `/duplicates/{id}/suggest` 500（把 id 列表误当 dict）；测试覆盖建议+清理（副本移入回收区、原件保留）；截图 `docs/screenshot_v3_duplicates.png` |
| T2-9 | 重复检测入口：`/api/dedup/start` + 页面按钮与进度 | `server.py`、`pages/DuplicatesPage.vue` | 三阶段检测（大小→快速哈希→完整哈希）跑在后台任务；测试：2 个同内容文件成组、独立文件不入选 |
| T2-10 | 历史页：回收区（恢复）+ 操作记录（撤销、类型筛选） | `pages/HistoryPage.vue` | 测试覆盖删除→回收区→恢复（文件回原位、库状态一致）；截图 `docs/screenshot_v3_recycle.png`、`docs/screenshot_v3_history.png` |
| T2-11 | 标签页：列表/新增/重命名/删除；修复 `rename_tag` | `pages/TagsPage.vue`、`database/models.py` | `rename_tag` 原先只改 `file_tags`，无关联文件的标签改名无效；改为事务内同步 `tags` 与别名；测试覆盖增删改（中文名 URL 编码）；截图 `docs/screenshot_v3_tags.png` |
| T2-12 | 设置页：AI 提供商增删改/默认/测试 + 运行信息 | `pages/SettingsPage.vue` | 模板快速创建、密钥掩码沿用；运行信息读 `/health`（版本/端口/PID）；截图 `docs/screenshot_v3_settings.png` |

## 关键数字（实测，Windows 11 / 12 核 / Python 3.14.9）

| 指标 | 当前值 | 目标 | 差距 |
|------|--------|------|------|
| 遍历（22k 文件） | 0.073 s（旧 0.119 s） | ≥1.5× | **1.64× 已达标** |
| SHA-256（164MB） | 冷盘 14.2× / 热缓存 2.2× | ≥2× | **已达标** |
| 语义检索 1 万×768 | ≈404 ms | ≤50 ms | 8× |
| 相似分组 1 万张 | ≈10.5 s | ≤400 ms | 26× |
| 逐行写入（应用层） | 0.18 ms/行 | 批量 0.052 ms/行 | 3×（已实现，未接入调用方） |
| 打包体积 | 539 MB（未压缩） | ≤300MB 安装包 | 安装包未实测 |

## 下一步（按顺序）

1. **AI 对话页**（P3 首块）：`/api/ai/chat/stream` 流式渲染 + 引用锚点 + 会话保存
2. **分类管理页**：`/api/classifications` 列表与批量改类
3. 之后：标签页、设置页、AI 对话（流式 + 引用）
3. 之后：AI 对话（流式 + 引用），再接扫描/重复/历史/标签/设置
4. **T1-1b（按需）**：`file_watcher` 等 Qt 模块仅在需要同等能力时才改

## 已知问题 / 技术债

| # | 问题 | 影响 | 计划 |
|---|------|------|------|
| 1 | NSIS 安装包未产出（electron-builder 下载二进制卡住） | 安装体积只有估算值 | 换网络或手动放缓存后补测 |
| 2 | ADR-001～013 只写在方案附录，没有独立文件 | 评审时缺决策留痕 | P4 前补齐 `docs/adr/` |
| 3 | `tests/` 中 11 个文件仍 import PyQt6 | 测试跑不全 | T1-1 完成后恢复 |
| 4 | 预览仅支持图片与纯文本，PDF/Office 未做 | 文档类只能看元数据 | 需要时用 PyMuPDF 渲染首页（服务端已装） |
| 5 | `content_indexer` 仍全表载入后切片 | 大库索引启动慢 | T1-4 剩余项 |
| 6 | 缩略图无磁盘/内存缓存，重复请求重复解码 | 列表滚动时 CPU 偏高 | P3 接入时加 LRU |
| 7 | `scan_time` 为 NULL 的旧数据会被 keyset 跳过 | 可能漏行 | 接 UI 前跑一次全库检查 |
| 8 | 排除 numpy/pymupdf4llm 可省约 30MB | 体积优化 | 可选，不阻塞 |
| 9 | 旧 PyQt6 界面仍走 `FileScanWorker`（未接入新内核） | 旧界面不享受提速 | 随 P3/P4 删旧 UI 自然消失；服务端已接新内核 |
| 10 | `dhash_many` 无真实图片集验证 | 相似图并行收益未证实 | 有图片语料后补测 |
| 11 | 组件总览页挂在主导航（`组件`） | 发布版不应出现 | P4 前移除入口，保留文件 |
| 12 | 筛选结果仍走 OFFSET 分页（keyset 仅用于无筛选列表） | 深页筛选会变慢（>5 万条时） | 若实测超 200ms，再为「按 modify_time 排序 + 固定筛选」补复合索引 |
| 13 | 只有深色主题，浅色未做 | 无法跟随系统外观 | token 已留好，补一套变量值即可（约半天） |
| 14 | 未安装 `vue-tsc`，`.vue` 模板无类型检查 | 模板里的字段拼错只能在运行时暴露 | 加一条 `npm run typecheck` |
| 15 | 没有 CI；首屏 JS 预算、基准回归都只在本机手工跑 | 回归无人守 | P4 前接最小 CI（构建 + pytest + 体积门禁） |
| 16 | 表格无排序、列宽拖拽、多选 | 大批量操作只能逐个点 | 等重复文件页出现多选需求时一起做 |
| 17 | 筛选条件不持久化，也没有"保存为智能集合" | 每次进来要重填 | 后端已有 `saved_queries` 表，接上即可 |
| 18 | 正文检索未端到端验证（库里没有内容索引数据） | `content` 分支可能有问题未被发现 | 造一份内容索引后补测试 |
| 19 | `/api/events` 无任务即断开，多客户端各拉快照 | 多窗口时重复轮询 | 有第二个窗口需求时改广播队列 |
| 20 | 表单控件用原生 `input/select`，未纳入组件库 | 日期控件在不同语言包下样式不一致 | 做表单页（扫描/设置）时统一封装 |
| 21 | 哈希阶段无进度（`collect` 后到入库前只报一次 0/total） | 2 万文件约 2s 停在 0% | 需要时把 `hash_many` 改成按块回调 |
| 22 | 扫描页"取消"按钮未端到端验证（仅 `TaskRunner.cancel` 单元测试） | 取消后 UI 状态可能不刷新 | 下次真机点一次并看 `status=cancelled` |
| 24 | "撤销"按钮未端到端验证（`/history/{id}/undo` 无测试） | 撤销失败时用户只看到报错 | 补一个删除→撤销→文件回原位的测试 |
| 25 | 回收区没有"永久删除 / 清空"入口 | 回收区只增不减，磁盘不会释放 | 需要时加，并做二次确认 |
| 26 | 标签页只能管理标签本身，不能给文件打标/解标 | 用户的标签只能靠旧 UI 或 API 产生 | 在文件页加"标签"列与批量打标 |
| 27 | 标签颜色/合并/别名管理未接 UI（接口已有） | 层级与配色能力闲置 | 需要时补 |
| 28 | 后端没有扫描目录的增删改接口，设置页无法管理扫描目录 | 用户无法在界面里增删监控目录 | 补 `/api/directories` CRUD（DAO 已就绪） |
| 29 | 设置页"测试连接"按钮未验证（需要真实 API Key） | 失败原因可能不友好 | 配好真实密钥后手测一次 |


## 决策记录（已确认）

| 决策 | 结论 |
|------|------|
| 技术路线 | A：Electron + Vue 3 + TS + Python sidecar |
| 计算 | Python 多进程 + numpy（不引入 Rust/Node 原生模块） |
| 前端库 | ECharts、markdown-it、DOMPurify |
| 体积 | ≤300MB 安装包（接受 Electron 运行时成本） |

## 自验命令

```bash
# 基准（含自检）
.venv/Scripts/python.exe bench/run_all.py --selftest
.venv/Scripts/python.exe bench/run_all.py --root bench/data/1k

# 数据层测试
.venv/Scripts/python.exe -m pytest tests/test_data_layer.py -q

# 桌面骨架
cd desktop && npm run build && npm run smoke
```

## 更新约定

每完成一个任务：更新「已完成」表格 + 首行完成度 + 「下一步」第一条；遇到阻塞写进「已知问题」。

**每段结束前必须核对一次本表**：当轮说过的"跳过/未做/风险"要全部落到这里，避免只留在对话里。核对记录写在本行下方。

该约定已写成项目规则 `.codebuddy/rules/progress-tracking.md`（`alwaysApply`），新会话同样生效；完成的债项直接删行，不要留勾。

| 核对时间 | 新增条目 | 说明 |
|----------|----------|------|
| 2026-11-19 | 13–20 | 补齐此前只在对话里提过、未落表的 8 项 |
| 2026-11-19 | 关闭 23 | 新增 `/api/dedup/start` 与重复页「检测重复」按钮，空页不再无路可走 |
