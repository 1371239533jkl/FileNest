# 项目进度

> 最后更新：2026-11-20　当前阶段：**P3/P4 并行**　总体完成度：约 96%
> 方案与验收标准见 `docs/REFACTOR_PLAN.md`；性能基线见 `docs/perf/BASELINE.md`。

## 一句话现状

P0 全部走完（度量、骨架、sidecar 握手、打包，含一次体积决策）；P1 只做了数据层，计算与服务化未动。

## 里程碑

| 阶段 | 状态 | 完成度 | 说明 |
|------|------|--------|------|
| P0 度量与骨架 | ✅ 完成 | 100% | NSIS 安装包未产出（网络阻塞），其余达成 |
| P1 服务化与数据治理 | 🟡 收尾 | 约 85% | 数据层 + 计算内核 + 扫描服务 + 任务/SSE + 缩略图/退出/token 已落地；剩 watcher 等按需项 |
| P2 渲染骨架与设计系统 | ✅ 完成 | 100% | 7 个页面 + 组件库 + 截图回归 |
| P3 页面迁移 | 🟡 进行中 | 约 62% | AI 对话/分类/清理/时间线已完成；归档、工作区未做 |
| P4 收尾（工程化） | 🟡 进行中 | 约 70% | 导航/CI/安装包/数据备份已落地；待办：安装器在干净机器实测、代码签名、自动更新 |
| P4 收尾与发布 | ⬜ 未开始 | 0% | — |

## 已完成（可验收）

| 编号 | 内容 | 证据 | 验收 |
|------|------|------|------|
| T0-1 | 基准套件（扫描/哈希/余弦/分组/SQLite/分页 + 自检） | `bench/run_all.py`、`--selftest` | 通过 |
| T0-2 | 固定种子数据集生成器 | `bench/gen_dataset.py` | 1,100 文件 / 85.1MB / seed 42 |
| T0-3 | 基线采集与报告 | `docs/perf/BASELINE.md`、`bench/results/baseline-1k.json` | 已入库（含一次口径修正） |
| T0-4 | Electron + Vue 3 + TS 骨架 | `desktop/` | `npm run build` 通过 |
| T0-5 | sidecar 握手（随机端口 / health / 杀进程树） | `desktop/src/main/sidecar.ts` | `npm run smoke` → PASS，无孤儿进程 |
| T0-6 | 打包链路（PyInstaller onedir + electron-builder） | `desktop/packaging/build-sidecar.cmd`、`package.json` | **NSIS 安装包 204.1MB**（预算 ≤300MB）；sidecar 182.1MB；`release\win-unpacked\FileNest.exe --smoke` 退出码 0、无残留进程 |
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
| T3-1 | AI 对话页：SSE 流式 + Markdown 渲染 + 净化 | `pages/ChatPage.vue`、`main/index.ts`、`lib/markdown.ts` | 主进程消费 SSE 并逐帧转发 IPC；markdown-it（`html:false`）+ DOMPurify；**已用真实模型验证流式渲染**；截图 `docs/screenshot_v3_chat.png`、`docs/screenshot_v3_markdown.png` |
| T3-2 | 对话上下文增强 | `web_api.py` | 整句匹配不到文件名时退化为"最近入库 20 条"，并在上下文里补 `modify_time`；实测模型能按时间排序给出文件清单 |
| T3-3 | 接入真实模型 | `ai_models.json`（本地，不入库） | 火山方舟 `deepseek-v4.1-flash`，`/providers/volc/test` 延迟 1076ms |
| T3-4 | 分类页：分布 + 规则增删启停 + 后台重跑分类 | `pages/ClassificationPage.vue`、`server.py` | 新增 `POST /classification/apply`（后台任务 + 进度）；测试覆盖分类落库；截图 `docs/screenshot_v3_classification.png` |
| T3-5 | 修复默认分类规则重复插入 | `database/db_manager.py` | 规则表无 `rule_name` 唯一键，`INSERT OR IGNORE` 每次启动重复插入（实测 195 行/7 个名字）；改为先按名去重、再补缺失项 |
| T3-6 | 清理中心：AI 洞察 + 分类筛选 + 勾选清理 | `pages/CleanupPage.vue` | 按类别筛选、全选当前、确认后移入回收区；截图 `docs/screenshot_v3_cleanup.png` |
| T3-7 | 修复 AI 洞察被截断 | `core/ai_layer.py` | `max_tokens=400` 对推理型模型不够（正文被思考吃光，实测返回空串）；提到 900 后输出 487 字完整分析（354+542 tokens / 7.6s） |
| T3-8 | 修复清理列表重复 | `web_api.py` | `/cleanup/analyze` 把 `all` 分组也展开，每个文件出现两次；改为跳过 `all` 并按 file_id 去重 |
| T3-9 | 时间线页：操作/外部事件统一视图 | `pages/TimelinePage.vue` | 按天分组、模式切换、类型筛选；实测 3 条删除记录（原路径 → 回收区路径）；截图 `docs/screenshot_v3_timeline.png` |
| T4-1 | 侧栏分组导航（替代顶部 12 个标签） | `renderer/App.vue` | 五组：概览/文件/智能/记录/系统；「组件」页仅开发构建可见；截图 `docs/screenshot_v3_dashboard.png` |
| T4-2 | 最小 CI（后端测试 + 前端构建 + 体积门禁） | `.github/workflows/ci.yml` | Windows runner；跑 5 个不依赖 PyQt6 的测试文件；主包 > 400KB 直接失败 |
| T4-3 | 打包链路验证（PyInstaller onedir + electron-builder dir） | `desktop/packaging`、`desktop/package.json` | sidecar 182.1MB；`release\win-unpacked\FileNest.exe --smoke` 退出码 0，残留进程 0（打包态下 sidecar 路径与 Job Object 清理均正常） |
| T4-4 | 数据安全：启动前按日备份 + 打开数据目录 | `database/db_manager.py`、`pages/SettingsPage.vue` | SQLite 在线备份（避开 WAL）；同日幂等、最多 3 份；实测生成 `filenest.db.bak-20261120` 17.6MB |

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

1. **时间线**：`/api/timeline` 操作与外部事件统一视图
2. **归档包 / 工作区**：`/api/archive`、`/api/workspaces`
3. 之后：DataTable 多选与批量操作（技术债 16）、P4 收尾（安装包、CI）
3. 之后：标签页、设置页、AI 对话（流式 + 引用）
3. 之后：AI 对话（流式 + 引用），再接扫描/重复/历史/标签/设置
4. **T1-1b（按需）**：`file_watcher` 等 Qt 模块仅在需要同等能力时才改

## 已知问题 / 技术债

| # | 问题 | 影响 | 计划 |
|---|------|------|------|
| 1 | sidecar 里 pymupdf 独占 93.2MB（超过一半），numpy 26MB | 安装包 204MB，进一步压缩空间有限 | 如需瘦身，把 PDF 解析做成可选组件按需下载 |
| 2 | ADR-001～013 只写在方案附录，没有独立文件 | 评审时缺决策留痕 | P4 前补齐 `docs/adr/` |
| 3 | `tests/` 中 11 个文件仍 import PyQt6 | 测试跑不全 | T1-1 完成后恢复 |
| 4 | 预览仅支持图片与纯文本，PDF/Office 未做 | 文档类只能看元数据 | 需要时用 PyMuPDF 渲染首页（服务端已装） |
| 5 | `content_indexer` 仍全表载入后切片 | 大库索引启动慢 | T1-4 剩余项 |
| 6 | 缩略图无磁盘/内存缓存，重复请求重复解码 | 列表滚动时 CPU 偏高 | P3 接入时加 LRU |
| 7 | `scan_time` 为 NULL 的旧数据会被 keyset 跳过 | 可能漏行 | 接 UI 前跑一次全库检查 |
| 8 | 排除 numpy/pymupdf4llm 可省约 30MB | 体积优化 | 可选，不阻塞 |
| 9 | 旧 PyQt6 界面仍走 `FileScanWorker`（未接入新内核） | 旧界面不享受提速 | 随 P3/P4 删旧 UI 自然消失；服务端已接新内核 |
| 10 | `dhash_many` 无真实图片集验证 | 相似图并行收益未证实 | 有图片语料后补测 |

| 12 | 筛选结果仍走 OFFSET 分页（keyset 仅用于无筛选列表） | 深页筛选会变慢（>5 万条时） | 若实测超 200ms，再为「按 modify_time 排序 + 固定筛选」补复合索引 |
| 13 | 只有深色主题，浅色未做 | 无法跟随系统外观 | token 已留好，补一套变量值即可（约半天） |
| 14 | 未安装 `vue-tsc`，`.vue` 模板无类型检查 | 模板里的字段拼错只能在运行时暴露 | 加一条 `npm run typecheck` |

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

| 31 | 首次对话约有 4 秒无响应（`_ai_layer()` 初始化慢） | 用户会以为卡住 | 页面加"思考中…"占位，或预热 AI 层 |
| 32 | 对话不保存，刷新即丢 | 无法回看历史问答 | 接 `sessions/` 持久化 |
| 33 | 分类规则只能增/删/启停，不能编辑（接口有 PUT 未接） | 改规则要删了重建 | 行内编辑，复用标签页的做法 |
| 34 | 分类页没有"手动改类"和批量选择 | 规则错了只能改规则重跑 | 依赖 DataTable 多选（技术债 16） |
| 35 | 清理中心每次进入都调用一次 AI 生成洞察（约 7-8s、消耗 token） | 反复切页会重复计费 | 缓存到 settings 并加"重新生成"按钮 |
| 36 | 清理规则的"旧文件"未命中（300 天前的 .log 也没被识别） | 该类别形同虚设 | 需要看 `_old_files` 的判定条件 |

| 38 | 时间线没有分页（一次 300 条封顶）且无按路径过滤入口 | 记录多时看不全 | 补分页或虚拟滚动 |
| 39 | 备份只有"按日自动 3 份"，没有手动备份/一键恢复入口 | 出问题时普通人不会手动改名恢复 | 设置页补「立即备份 / 从备份恢复」 |
| 40 | 安装包未签名、也未在干净机器上真实安装过 | 用户会看到"未知发布者"拦截；安装流程未验证 | 需要证书或至少补一份图文安装说明 |


## 决策记录（已确认）

| 决策 | 结论 |
|------|------|
| 技术路线 | A：Electron + Vue 3 + TS + Python sidecar |
| 计算 | Python 多进程 + numpy（不引入 Rust/Node 原生模块） |
| 前端库 | ECharts、markdown-it、DOMPurify |
| 体积 | ≤300MB 安装包（接受 Electron 运行时成本） |

## 回滚与数据安全

| 层级 | 手段 | 触发条件 |
|---|---|---|
| 功能级 | 删除/去重/清理都是"移入回收区"，可在历史页恢复；AI 提供商可随时切换 | 单项能力异常 |
| 版本级 | 直接用旧安装包覆盖安装（NSIS 非一键安装，可指定目录） | 新版整体不可用 |
| 数据级 | 每次启动前自动备份 `filenest.db.bak-YYYYMMDD`，保留最近 3 份；用 SQLite 在线备份接口，避免 WAL 未落盘的数据丢失 | 误操作或升级后数据异常 |
| 迁移/导出 | 设置页「打开数据目录」，卸载不删除数据库文件 | 换机、迁移 |

实测：`%APPDATA%\FileNest\` 下已生成 `filenest.db.bak-20261120`（17.6 MB）；同一日期重复启动不会重复生成，最多保留 3 份。

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
| 2026-11-20 | 关闭 30 | 用真实模型（火山方舟 deepseek-v4.1-flash）验证流式渲染与上下文增强 |
| 2026-11-20 | 关闭 11/15/37 | 组件页改为仅开发可见；新增最小 CI（含体积门禁）；顶部导航改侧栏分组 |
| 2026-11-20 | 关闭 1 | NSIS 安装包产出（204.1MB），打包态冒烟通过；体积问题转为新条目 |
