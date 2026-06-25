# 智能文件管家 AI 集成架构方案

## 文档状态

| 版本 | 日期 | 状态 |
|------|------|------|
| v1.0 | 2026-06-25 | 方案设计阶段 |

---

## 一、技术栈现状

| 层级 | 技术 |
|------|------|
| 语言 | Python 3.11+ |
| 界面框架 | PyQt6 |
| 数据库 | MySQL 8.x (PyMySQL) |
| 现有 AI | 纯启发式规则引擎 (`core/rule_engine.py`) |
| 部署形态 | Windows/macOS/Linux 桌面应用 |

**现有规则引擎提供三层功能但均依赖字符串匹配和正则，不调用 LLM：**
- `NLSearchParser` — 自然语言搜索解析
- `TagRecommender` — 基于文件名/路径模式的标签推荐
- `CleanupAdvisor` — 清理建议

---

## 二、AI 核心应用场景（4 大场景 + 优先级）

按对文件管理体验的提升程度排序：

| 优先级 | 场景 | 当前状态 | AI 升级后效果 |
|--------|------|---------|-------------|
| P0 | **智能文件搜索** | 正则 NL 解析 (40% 命中率) | LLM 理解复杂意图 (90%+ 命中率) |
| P0 | **标签推荐** | 固定规则匹配 | LLM 理解文件内容语义，推荐精准标签 |
| P1 | **文件重命名建议** | 无 | 根据文件内容/上下文建议有意义的命名 |
| P1 | **智能清理建议** | 固定阈值规则 | LLM 分析文件使用模式，给个性化清理建议 |
| P2 | **文件内容摘要** | 无 | 自动生成文档/代码/图片的文本描述 |
| P2 | **分类规则生成** | 手动配置 | LLM 从用户行为学习并生成分类规则 |
| P3 | **重复文件判断** | 仅哈希比对 | LLM 辅助判断相似文件是否需要保留 |
| P3 | **自然语言问答** | 无 | "上周我修改了哪些文档？哪个文件夹占用最大？" |

### 场景详细定义

**P0-1：智能文件搜索（升级 NLSearchParser）**

```
用户输入: "帮我找一下去年夏天在成都拍的那些美食照片，不要大于5M的"
当前规则引擎: 能解析出 type=image, date≈last_year, 但"成都""美食"可能被当name模糊匹配
LLM 升级: 输出结构化 JSON → {type: image, keywords: ["成都","美食"], 
         date_range: ["2025-06","2025-08"], max_size: 5MB, path_hint: "相机/照片"}
```

**P0-2：智能标签推荐（升级 TagRecommender）**

```
当前规则引擎: 匹配文件名中的"报告""合同"等关键词，置信度公式固定
LLM 升级: 传入文件名+路径+扩展名+元数据摘要 → 返回带语义理解的标签
  例: "2025Q4-financial-summary-v3-final.xlsx" 
      → [财务报告, Q4, Excel, 终稿] (置信度: 0.95, 0.9, 0.95, 0.85)
```

**P1-1：智能重命名建议**

```
输入: 文件路径 + 元数据
输出: 3-5 个重命名建议
  例: IMG_8743.jpg (EXIF: 2025-08-15, 成都太古里, Canon EOS R5)
      → ["20250815-成都太古里-街拍.jpg", "2025夏-成都太古里-夜景.jpg", ...]
```

**P1-2：智能清理建议（升级 CleanupAdvisor）**

```
当前: 固定规则 → 文件>1年未修改=建议归档
LLM 升级: 分析文件名模式+修改频率+目录结构 → 更精准的建议
  例: "report_backup_jan.zip" 在 \Archive\ 下 2年未动 → 高置信度可删除
      "photo_edit_v2.psd" 在 \Projects\ 但兄弟目录有 v3.psd → 建议删除旧版
```

**P2-1：文件内容摘要**

```
支持类型: .txt/.md/.pdf/.docx/.py/.java
输入: 文件前 4000 字符
输出: 50-100 字中文摘要
```

---

## 三、模型接入策略

### 3.1 混合架构设计

```
┌──────────────────────────────────────────────────────────┐
│                    AILayer (core/ai_layer.py)            │
│                                                          │
│  ┌─────────────────┐  ┌─────────────────┐               │
│  │ LocalBackend    │  │ CloudBackend    │   ← 抽象接口  │
│  │ (Ollama/llama)  │  │ (OpenAI/Claude) │               │
│  └────────┬────────┘  └────────┬────────┘               │
│           │                    │                         │
│  ┌────────┴────────────────────┴────────┐               │
│  │         ModelRouter                  │               │
│  │  根据场景+成本+模型能力自动选后端      │               │
│  └──────────────────┬──────────────────┘                │
│                     │                                    │
│  ┌──────────────────┴──────────────────┐                │
│  │         FallbackChain               │               │
│  │  LLM → 本地模型 → 规则引擎 (兜底)     │               │
│  └─────────────────────────────────────┘               │
└──────────────────────────────────────────────────────────┘
```

### 3.2 后端对比分析

| 维度 | 本地开源 (Ollama + qwen2.5) | 云端闭源 (GPT-4o/Claude) |
|------|---------------------------|------------------------|
| **部署** | 下载模型文件，Ollama 一键启动 | 仅需 API Key，零部署 |
| **隐私** | 完全离线，数据不出本机 | 数据发送到 OpenAI/Anthropic 服务器 |
| **延迟** | 2-15 秒 (依硬件) | 1-5 秒 |
| **成本** | 免费（需 8GB+ 显存/内存） | $0.15-$15/百万 token |
| **中文能力** | qwen2.5:7b 良好，72b 优秀 | GPT-4o / Claude 3.5 顶级 |
| **文件理解** | 需另外搭建 RAG | 内置长上下文 + 多模态 |
| **离线可用** | 是 | 否（必须联网） |
| **硬件要求** | 7B 模型需 8GB 显存或 16GB 内存 | 无 |

### 3.3 推荐的分层策略

```
场景分层:
  P0 场景 (搜索/标签推荐):
    主: 本地 qwen2.5:7b (低延迟、免费、隐私)
    辅: 用户可配置云端 API 提升效果

  P1 场景 (重命名/清理):
    主: 本地 qwen2.5:7b  
    可一次性批处理，无需实时性

  P2 场景 (摘要/规则生成):
    主: 本地模型 (批处理)
    可选择性使用云端模型提升质量

  P3 场景 (问答/深度分析):
    主: 云端模型 (需要强大的推理和多步分析)
    本地模型做降级备选
```

### 3.4 本地模型推荐

| 模型 | 大小 | 内存需求 | 中文能力 | 适合场景 |
|------|------|---------|---------|---------|
| `qwen2.5:7b-instruct` | 4.4GB | 8GB RAM | 优秀 | 搜索/标签/重命名 |
| `qwen2.5:14b-instruct` | 8.5GB | 16GB RAM | 优秀 | 摘要/规则生成 |
| `llama3.1:8b-instruct` | 4.7GB | 8GB RAM | 良好 | 通用备选 |
| `mistral:7b-instruct` | 4.1GB | 8GB RAM | 一般 | 英文场景备选 |

**推荐默认模型**: `qwen2.5:7b-instruct` — 中文最优、体积适中、Ollama 支持完善。

---

## 四、数据交互流程

### 4.1 整体流程

```
用户输入
  │
  ▼
┌─────────────────┐
│  1. 预处理层     │  ← 文本清洗、意图分类、敏感词过滤
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  2. 上下文组装   │  ← 系统提示词 + 用户输入 + 文件元信息 + 历史对话
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  3. ModelRouter  │  ← 选择后端 + 构造 API 请求
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  4. LLM 调用     │  ← 发送请求，流式接收响应
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  5. 响应解析     │  ← JSON 提取 + 格式校验 + Schema 验证
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  6. 安全审核     │  ← 输出过滤 + 脱敏 + 合规检查
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  7. 结果执行     │  ← 应用到文件操作 (搜索/加标签/重命名)
└─────────────────┘
```

### 4.2 关键组件设计

#### 4.2.1 预处理层 (`Preprocessor`)

```python
class Preprocessor:
    def process(self, user_input: str) -> dict:
        # 1. 安全扫描: 检测注入、恶意提示词
        # 2. 意图分类: 搜索/标签/重命名/清理/问答
        # 3. 文本规范化: 去除多余空白、统一标点
        # 4. 提取上下文: 如果有选中文件，注入文件元信息
        return {
            'intent': 'search',          # 意图类型
            'clean_text': '...',          # 清洗后文本
            'context_files': [...],       # 关联文件ID列表
            'detected_entities': {...},   # 实体识别 (日期/大小/类型)
        }
```

#### 4.2.2 提示词工程 (`PromptBuilder`)

按场景设计专用 System Prompt，避免通用提示词导致幻觉。

**搜索场景 System Prompt 示例：**
```
你是一个文件搜索助手。用户用自然语言描述要找的文件。你需要将意图解析为 JSON。

规则:
1. file_type 必须是: image/document/code/video/audio/archive/executable/font
2. 日期格式: YYYY-MM-DD
3. size 单位: bytes
4. name 是文件名关键词(可多选，用 | 分隔)

输出 JSON 格式(不要输出其他内容):
{
  "name": "关键词1|关键词2",
  "file_type": "image",
  "extension": ".jpg",
  "min_size": null,
  "max_size": 5242880,
  "start_date": "2025-01-01",
  "end_date": "2025-12-31",
  "explanation": "正在搜索: 2025年的图片，大小不超过5MB"
}

用户查询: {user_input}
当前时间: {current_time}
```

**标签推荐场景 System Prompt：**
```
你是一个文件标签专家。根据文件信息，推荐最合适的标签。

标签规则:
- 标签应该简洁（2-6个字）
- 从文件名、路径、类型、大小综合判断
- 避免过于泛化的标签（如"文件"、"数据"）
- 每个标签附置信度分数 (0.0-1.0)

输出 JSON 格式:
{
  "tags": [{"name": "标签名", "confidence": 0.95}, ...]
}

文件信息:
- 文件名: {file_name}
- 路径: {file_path}
- 类型: {file_type}
- 大小: {file_size}
- 扩展名: {extension}
- 修改时间: {modify_time}
```

#### 4.2.3 上下文管理器 (`ContextManager`)

```python
class ContextManager:
    """管理对话历史和上下文窗口"""
    
    def __init__(self, max_tokens: int = 4096):
        self.history: list[dict] = []     # 对话历史
        self.max_tokens = max_tokens
    
    def add_turn(self, user_msg: str, assistant_msg: str):
        """添加一轮对话，超出容量时自动裁剪早期轮次"""
        
    def build_context(self, system_prompt: str, user_input: str,
                      file_context: list[dict] = None) -> list[dict]:
        """组装最终的 messages 列表发给 LLM"""
        messages = [{"role": "system", "content": system_prompt}]
        # 注入文件上下文（元数据摘要）
        # 注入最近 N 轮对话（自动裁剪）
        messages.append({"role": "user", "content": user_input})
        return messages
```

#### 4.2.4 响应解析器 (`ResponseParser`)

```python
class ResponseParser:
    """从 LLM 响应中提取结构化数据"""
    
    @staticmethod
    def extract_json(text: str) -> dict:
        """从 LLM 输出中提取 JSON 块（处理 markdown code fence、不完整 JSON 等）"""
        # 1. 尝试直接 json.loads
        # 2. 提取 ```json ... ``` 代码块
        # 3. 提取 { ... } 最外层
        # 4. 尝试修复尾部截断的不完整 JSON
    
    @classmethod
    def parse_search_result(cls, text: str) -> SearchParams:
        """解析搜索 LLM 响应为 SearchParams"""
        data = cls.extract_json(text)
        return SearchParams(
            name=data.get('name'),
            file_type=data.get('file_type'),
            # ... 其他字段
        )
```

---

## 五、异常处理与安全机制

### 5.1 多层降级策略

```
LLM 调用失败时：
  Attempt 1: 云端 API (2s 超时)
  ├── 成功 → 直接使用结果
  └── 失败 → Attempt 2: 本地模型 (10s 超时)
       ├── 成功 → 使用结果 + 记录升档
       └── 失败 → Attempt 3: 规则引擎 (立即)
            └── 使用规则引擎结果 + 告知用户"AI 暂时不可用，使用本地规则"
```

### 5.2 异常处理矩阵

| 异常类型 | 处理策略 | 用户提示 |
|---------|---------|---------|
| 网络超时 (API) | 降级到本地模型 | "云端服务响应慢，已切换本地模型" |
| 本地模型 OOM | 降级到规则引擎 | "本地模型内存不足，已使用规则引擎" |
| API Key 无效 | 切换本地模型 + 通知用户配置 | "请检查 API Key 配置" |
| 响应格式异常 | 重试 1 次 → 规则引擎兜底 | "AI 返回格式异常，已使用备用方案" |
| Token 超限 | 截断输入 → 重试 | 无感知 (内部处理) |
| 并发请求过载 | 请求排队 (FIFO 队列) | "正在处理中..." |
| 内容审核触发 | 拒绝执行 + 安全提示 | "检测到不安全输入，已拒绝" |

### 5.3 内容安全审核 (`SafetyFilter`)

```python
class SafetyFilter:
    """输入输出安全审核"""
    
    # 注入攻击检测模式
    INJECTION_PATTERNS = [
        r'ignore (all )?previous (instructions|prompts?)',
        r'you are now .*(DAN|jailbreak|evil|unrestricted)',
        r'system:\s*',  # 伪系统消息注入
        r'\[INST\].*\[/INST\]',  # 伪指令标签
    ]
    
    # 文件操作敏感词（禁止 LLM 输出中包含危险操作）
    DANGEROUS_OUTPUT = [
        r'rm\s+-rf', r'format\s+[cC]:', r'del\s+/[fF]',
        r'DROP\s+TABLE', r'DELETE\s+FROM',
    ]
    
    def check_input(self, text: str) -> tuple[bool, str]:
        """检查用户输入是否包含注入攻击"""
    
    def check_output(self, text: str) -> tuple[bool, str]:
        """检查 LLM 输出是否包含敏感内容/危险命令"""
```

### 5.4 输出校验 (`OutputValidator`)

```python
class OutputValidator:
    """校验 LLM 输出的结构正确性和安全性"""
    
    def validate_search_params(self, params: dict) -> tuple[bool, list[str]]:
        """校验搜索参数: file_type 必须在白名单内、日期格式正确、size 非负"""
        errors = []
        # file_type 白名单
        # 日期范围合理性 (start < end)
        # size 非负
        return len(errors) == 0, errors
    
    def validate_tags(self, tags: list) -> tuple[bool, list[str]]:
        """校验标签: 长度限制、不含特殊字符"""
```

### 5.5 并发控制 (`RequestQueue`)

```python
class RequestQueue:
    """LLM 请求队列，防止并发过载"""
    
    def __init__(self, max_concurrent: int = 2, max_queue: int = 10):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.pending: list[asyncio.Task] = []
    
    async def submit(self, coro) -> Any:
        """提交 LLM 请求，超出队列容量时返回队列满提示"""
```

---

## 六、性能与成本评估

### 6.1 延迟分析

| 场景 | 输入 Token | 本地 7B (RTX 3060) | 本地 7B (CPU) | GPT-4o API |
|------|-----------|-------------------|--------------|------------|
| 搜索解析 | ~200 | 1-3s | 3-8s | 1-2s |
| 标签推荐 (单文件) | ~150 | 1-2s | 2-5s | 0.5-1s |
| 标签推荐 (批量50) | ~500 | 3-6s | 8-15s | 2-4s |
| 重命名建议 | ~200 | 1-3s | 3-8s | 1-2s |
| 清理报告 | ~800 | 4-8s | 10-20s | 2-5s |
| 文件摘要 | ~500 | 2-5s | 5-12s | 1-3s |

### 6.2 成本测算（月活用户）

假设日均 200 次 LLM 调用（搜索为主），30% 为复杂查询用云端：

| 方案 | 月调用量 | 月成本 | 年成本 |
|------|---------|--------|--------|
| 纯本地 | 6000 次 | ¥0 | ¥0 |
| 纯云端 GPT-4o | 6000 次 | ~$3-8 | ~$50-100 |
| 混合 (70% 本地 + 30% 云端) | 1800 云 + 4200 地 | ~$1-3 | ~$15-36 |
| 纯云端 Claude | 6000 次 | ~$5-15 | ~$75-225 |

### 6.3 优化建议

**模型层面：**
1. **量化**: 使用 Q4_K_M 量化将 7B 模型压缩至 4.7GB，显存需求从 8GB 降至 6GB
2. **批处理**: 标签推荐合并为批次（50 文件/次）代替逐文件调用
3. **缓存**: 相似查询结果缓存 5 分钟，减少重复调用

**系统层面：**
1. **预加载**: 应用启动时后台加载模型，hide 首次调用冷启动延迟
2. **流式输出**: 使用 streaming API，用户在 500ms 内看到首个 token
3. **请求合并**: 连续快速输入时，防抖 300ms 后发送最新请求
4. **智能路由**: 简单关键词查询直接走规则引擎（零延迟），复杂意图走 LLM

**缓存策略：**
```python
# 搜索解析缓存
search_cache = LRUCache(maxsize=200, ttl=300)  # 5min TTL
# 标签推荐缓存 (按文件名+路径哈希)
tag_cache = LRUCache(maxsize=1000, ttl=1800)  # 30min TTL
# 文件摘要缓存 (永久，直到文件内容变化)
summary_cache = PersistentCache(path='~/.smart_fm/cache/ai_summaries.db')
```

---

## 七、实现路线图

### Phase 1: 基础设施（1-2 周）

```
├── core/ai_layer.py         ← AI 抽象层 + ModelRouter + FallbackChain
├── core/ai_backends.py      ← LocalBackend (Ollama) + CloudBackend (OpenAI)
├── core/ai_preprocessor.py  ← Preprocessor + SafetyFilter + OutputValidator
├── core/ai_prompts.py       ← 各场景 Prompt 模板
├── core/ai_context.py       ← ContextManager
├── core/ai_response.py      ← ResponseParser
├── core/ai_queue.py         ← RequestQueue (并发控制)
├── config.py                ← 新增 AI 配置段
├── .env.example             ← 新增 OPENAI_API_KEY / OLLAMA_HOST
```

### Phase 2: 场景接入（2-3 周）

```
├── 升级 NLSearchParser  → 优先 LLM，降级规则引擎
├── 升级 TagRecommender  → LLM + 规则引擎融合
├── 升级 CleanupAdvisor  → LLM 增强分析
├── 新增 RenameAdvisor   → 智能重命名建议
├── 新增 FileSummarizer  → 内容摘要生成
```

### Phase 3: 体验优化（1-2 周）

```
├── 流式输出（打字机效果）
├── 请求防抖 + 缓存
├── 模型热切换 UI（设置页）
├── 模型下载引导
```

---

## 八、配置设计

`config.py` 新增 AI 配置段：

```python
# ── AI 配置 ──
AI_ENABLED = True

# 后端选择: "local" | "cloud" | "hybrid" | "off"
AI_BACKEND = "hybrid"

# 本地模型配置
AI_LOCAL_HOST = "http://localhost:11434"  # Ollama 默认地址
AI_LOCAL_MODEL = "qwen2.5:7b-instruct"
AI_LOCAL_TIMEOUT = 30  # 秒

# 云端 API 配置（可选）
AI_CLOUD_PROVIDER = "openai"  # openai | anthropic | custom
AI_CLOUD_API_KEY = os.getenv("SMART_FM_OPENAI_KEY", "")
AI_CLOUD_MODEL = "gpt-4o-mini"  # 性价比优先
AI_CLOUD_BASE_URL = "https://api.openai.com/v1"
AI_CLOUD_TIMEOUT = 15

# 缓存配置
AI_CACHE_ENABLED = True
AI_CACHE_TTL_SEARCH = 300   # 搜索缓存 5 分钟
AI_CACHE_TTL_TAGS = 1800    # 标签缓存 30 分钟

# 安全配置
AI_MAX_INPUT_CHARS = 4000
AI_MAX_OUTPUT_TOKENS = 512
AI_CONTENT_SAFETY = True
```

---

## 九、关键模块接口定义

```python
# core/ai_layer.py

class AILayer:
    """AI 层统一入口，封装所有 LLM 交互"""
    
    def __init__(self, config: dict):
        self.router = ModelRouter(config)
        self.preprocessor = Preprocessor()
        self.safety = SafetyFilter()
        self.validator = OutputValidator()
        self.fallback = FallbackChain()
    
    async def search(self, query: str) -> SearchResult:
        """智能搜索: NL→结构化参数"""
        # 简单查询直接走规则引擎
        if self.preprocessor.is_simple(query):
            return self.fallback.search(query)
        return await self._call(fn=self.router.search, query=query, ...)
    
    async def recommend_tags(self, file_record: dict) -> list[Tag]:
        """标签推荐"""
    
    async def suggest_rename(self, file_record: dict) -> list[str]:
        """重命名建议"""
    
    async def analyze_cleanup(self) -> CleanupReport:
        """清理分析报告"""
    
    async def summarize(self, file_record: dict) -> str:
        """文件内容摘要"""
    
    async def _call(self, fn, **kwargs):
        """统一调用入口，封装降级/重试/监控"""
        for attempt in [Attempt.CLOUD, Attempt.LOCAL, Attempt.FALLBACK]:
            try:
                result = await fn(**kwargs)
                if self.safety.check_output(result)[0]:
                    return result
            except Exception as e:
                logger.warning(f"AI call failed: {attempt} → {e}")
                continue
        return self.fallback.default_result()
```

---

## 十、风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 本地模型下载失败 | 中 | 功能降级 | 提供分步引导、备选模型列表、规则引擎兜底 |
| LLM 输出不稳定 | 高 | 搜索结果不准 | Schema 校验 + 正则兜底 + 重试机制 |
| 用户数据隐私顾虑 | 中 | 用户不信任 | 默认本地模型，云端明确告知并征得同意 |
| 云端 API 费用超预期 | 低 | 成本失控 | 用量监控 + 月度限额 + 默认限制云端调用频率 |
| 模型包含偏见/不安全输出 | 低 | 声誉风险 | SafetyFilter + OutputValidator 多层过滤 |

---

## 附录 A：依赖清单

```
# AI 功能新增依赖
ollama>=0.1.0          # 本地模型运行时 (用户自行安装)
openai>=1.0.0          # OpenAI API SDK (可选)
httpx>=0.27.0          # 异步 HTTP 客户端
pydantic>=2.0.0        # 数据验证
tiktoken>=0.5.0        # Token 计数
cachetools>=5.3.0      # LRU 缓存
```

## 附录 B：Ollama 部署指南

```bash
# 1. 安装 Ollama (macOS/Linux)
curl -fsSL https://ollama.com/install.sh | sh

# 2. Windows: 下载安装包 https://ollama.com/download/windows

# 3. 拉取推荐模型
ollama pull qwen2.5:7b-instruct

# 4. 验证
ollama run qwen2.5:7b-instruct "你好，请用一句话介绍自己"

# 5. 启动服务 (默认 http://localhost:11434)
ollama serve
```
