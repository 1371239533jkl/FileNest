# FileNest 功能进度追踪

> 对照 `docs/FEATURE_ROADMAP.md` 的完成状态清单、批次任务与执行日志。
> 维护方式：每完成一个功能/批次，更新状态列并追加一条执行日志。

- 最后核对：2026-07-22
- 测试基线：`python -m pytest tests` → **99 passed**（全部通过）
- 状态图例：✅ 已完成 ｜ 🔶 部分完成（括号内注明缺口）｜ ⬜ 未开始

## 1. 完成状态总览

### P0 核心功能

| 编号 | 功能 | 状态 | 现有实现（证据） | 缺口 |
|---|---|---|---|---|
| P0-01 | 实时增量索引 | 🔶 | `core/file_watcher.py`：watchdog 监控、2s 防抖合并事件、忽略规则；`scan_tab.py` 变化提示 | 仅"提示手动扫描"，未自动落库；无失败重试 |
| P0-02 | 统一任务中心 | ✅ | `core/task_manager.py` + `ui/task_center.py`：排队/进度/取消/失败详情/重试 | — |
| P0-03 | 索引健康检查与修复 | ✅ | `core/index_health.py`：inspect + 保守 repair（只修复确认缺失记录） | — |
| P0-04 | 内容全文索引 | ✅ | `core/content_indexer.py` + `file_content_fts` 表 + `FileContentDAO`，复用 `file_reader.py` | — |
| P0-05 | 高级搜索语法 | 🔶 | `core/rule_engine.py` NLSearchParser + `ui/search_tab.py` 高级搜索条件区 | 语法提示/错误定位/结构化回显需确认补全 |
| P0-06 | 智能集合 | 🔶 | `ui/search_tab.py`：集合保存/删除/应用（存 QSettings） | 未用 `saved_queries` 表，无 DAO；"不移动真实文件"满足 |
| P0-07 | 批量重命名预览 | ✅ | `core/file_manager.py` `preview_batch_rename()` + `ui/classify_tab.py` 预览确认 | — |
| P0-08 | 可视化整理规则 | 🔶 | `database/models.py` ClassificationRuleDAO + `core/file_classifier.py` 加载数据库规则 | UI 层未见规则管理界面（条件/动作可视化构建） |
| P0-09 | 操作计划与预演 | 🔶 | `file_manager.py` `preview_move()`/`preview_batch_rename()`；回收区恢复预演 | 无独立 `OperationPlan` 应用模型；AI 整理计划未映射 |
| P0-10 | 存储空间分析 | ✅ | `ui/dashboard_tab.py` + `ui/chart_widgets.py` + FileDAO 统计 | — |
| P0-11 | 多阶段重复检测 | 🔶 | `core/dedup_manager.py`：按完整 SHA256 哈希分组 + 保留策略 | 无 大小→快速哈希→完整哈希 多阶段；无 hash_state 续算 |
| P0-12 | 安全清理中心 | 🔶 | `core/rule_engine.py` CleanupAdvisor + `ui/scan_tab.py` 清理建议报告 | 无聚合中心 UI（重复/临时/空/未用/超大）；排除目录、误报反馈、默认回收区流程待确认 |

### P1 增值功能

| 编号 | 功能 | 状态 | 现有实现（证据） | 缺口 |
|---|---|---|---|---|
| P1-01 | 语义搜索 | ⬜ | 仅 `ai_layer.py` `rank_by_relevance()`（LLM 相关性排序，非向量） | 无 `embedding_service.py`、无向量索引适配器 |
| P1-02 | 带引用的文件问答 | ✅ | `core/ai_tools.py` `search_content` 工具返回 `[来源 N]` + 摘录；`ai_chat_page.py` 正文检索 | — |
| P1-03 | AI 整理计划 | 🔶 | `ai_layer.py` `suggest_classify_rules()`；AI 标签/重命名建议（`ai_file_actions.py`） | 未映射为 `OperationPlan` 校验-预览-确认闭环 |
| P1-04 | 本地 AI Provider | ⬜ | `core/ai_backends.py` 仅 `OpenAICompatibleBackend` | 无 Ollama 等本地 Provider、状态检测、降级 |
| P1-05 | AI 隐私控制台 | 🔶 | `core/ai_preprocessor.py`：输入清洗、注入检测、危险输出检测 | 无目录级禁止、字段脱敏、调用记录、数据去向展示 |
| P1-06 | OCR 内容提取 | ⬜ | — | 全新 |
| P1-07 | 相似图片检测 | ⬜ | — | 全新 |
| P1-08 | 文件版本关系 | ⬜ | — | 全新（无 `file_relations` 表） |
| P1-09 | 文件夹画像 | ⬜ | — | 全新 |
| P1-10 | 标签层级与别名 | ⬜ | `database/models.py` TagDAO 仅平铺标签 | 无父子/同义词/颜色/合并 |
| P1-11 | 时间线与活动审计 | 🔶 | `operation_history` + `ui/history_tab.py`；dashboard"最近活动" | 无统一时间线（外部变化+应用操作混合视图、筛选） |
| P1-12 | 一键归档包 | ⬜ | — | 全新 |
| P1-13 | 工作区配置 | ⬜ | — | 全新 |
| P1-14 | Shell 与 CLI 集成 | ⬜ | `main.py` 无 argparse | 全新 |

### P2 远期功能

全部 ⬜ 未开始（P2-01 插件系统 ～ P2-09 自动化开放接口），按需择批。

## 2. 批次任务

> 按 roadmap「推荐版本路线」分组。每个批次可独立执行，执行前先说"执行批次 N"。
> 批次内任务完成一项即更新第 3 节日志。

### 批次 1：底座稳定收尾（对应 Phase 1）
| 任务 | 说明 | 状态 |
|---|---|---|
| 1-1 增量索引自动落库 | file_watcher 事件 → 自动增量更新 files 表；失败重试；事件风暴合并 | ⬜ |
| 1-2 内容索引增量/失败隔离确认 | content_indexer 按修改指纹增量、单文件失败不阻断（补测试） | ⬜ |

### 批次 2：搜索与组织补全（对应 Phase 2）
| 任务 | 说明 | 状态 |
|---|---|---|
| 2-1 高级搜索语法完善 | 语法提示、错误定位、结构化条件回显、特殊字符容错 | ⬜ |
| 2-2 智能集合入库 | 新增 `saved_queries` 表 + DAO，替换 QSettings 存储 | ⬜ |
| 2-3 可视化整理规则 UI | 规则列表 + 条件/动作编辑器 + 启停/排序/作用域/冲突检测 + 测试执行 | ⬜ |
| 2-4 操作计划模型 | 新增 `OperationPlan`：影响范围/冲突/不可逆项/释放空间/过期重校验 | ⬜ |

### 批次 3：空间治理完善（对应 Phase 3）
| 任务 | 说明 | 状态 |
|---|---|---|
| 3-1 多阶段重复检测 | 大小→快速哈希→完整哈希三级确认；hash_state 字段；中断续算 | ⬜ |
| 3-2 安全清理中心 | 聚合重复/临时/空/长期未用/超大；原因说明；默认回收区；排除目录；误报反馈 | ⬜ |

### 批次 4：可信 AI（对应 Phase 4）
| 任务 | 说明 | 状态 |
|---|---|---|
| 4-1 语义搜索 | `embedding_service.py` + 可替换向量索引适配器；可与结构化筛选组合；可关闭 | ⬜ |
| 4-2 AI 整理计划闭环 | AI 输出 → `OperationPlan` 校验/预览/确认；AI 无直接写权限 | ⬜ |
| 4-3 本地 AI Provider | `ai_backends.py` 增加 Ollama；状态检测/模型切换/自动降级 | ⬜ |
| 4-4 AI 隐私控制台 | 数据去向展示、目录级禁止、字段脱敏、调用记录 | ⬜ |

### 批次 5：内容理解（对应 Phase 5）
| 任务 | 说明 | 状态 |
|---|---|---|
| 5-1 OCR 内容提取 | 可选 OCR Provider → 内容索引；识别语言/置信度记录；失败不阻断 | ⬜ |
| 5-2 相似图片检测 | 感知哈希 + SimilarityManager；区分完全重复/视觉相似；阈值可调 | ⬜ |
| 5-3 文件版本关系 | `file_relations` 表；名称+时间+内容指纹；人工确认/解除 | ⬜ |
| 5-4 文件夹画像 | 复用统计 DAO + AI 洞察；无 AI 时规则统计 | ⬜ |
| 5-5 标签层级与别名 | 父子标签、同义词、颜色、合并；防循环；旧数据兼容 | ⬜ |

### 批次 6：工作流扩展（对应 Phase 6）
| 任务 | 说明 | 状态 |
|---|---|---|
| 6-1 时间线与活动审计 | 汇总外部变化+应用操作；时间/目录/类型筛选 | ⬜ |
| 6-2 一键归档包 | ArchiveService：清单+摘要+校验值；空间检查；失败清理 | ⬜ |
| 6-3 工作区配置 | `workspaces` 表；规则/标签/AI 权限按目录隔离 | ⬜ |
| 6-4 CLI 集成 | 轻量 CLI：搜索/扫描/标签；写操作继承安全校验与审计；JSON 输出 | ⬜ |

### 批次 7：平台化（P2，按需选择）
P2-01 插件系统、P2-02 NAS/云盘适配、P2-03 多设备索引聚合、P2-04 加密配置同步、
P2-05 知识图谱、P2-06 跨模态搜索、P2-07 生命周期策略、P2-08 团队协作权限、P2-09 自动化开放接口。

## 3. 执行日志

> 每完成一部分，在此追加一条记录（时间 / 完成内容 / 验证结果）。

| 日期 | 内容 | 验证 |
|---|---|---|
| 2026-07-22 | 对照 ROADMAP 完成全量盘点；建立本进度文档；测试基线 99 passed | ✅ |
