<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppButton from '../components/AppButton.vue'
import Panel from '../components/Panel.vue'
import { formatBytes, formatCount } from '../lib/format'
import { renderMarkdown } from '../lib/markdown'

interface Item {
  file_id: number
  file_path: string
  file_name: string
  file_size: number
  category: string
  reason: string
}

const CATEGORY_NAMES: Record<string, string> = {
  duplicates: '重复文件',
  temp: '临时文件',
  empty: '空文件',
  old: '旧文件',
  large: '大文件',
  all: '全部',
  manual: '手动选择',
}

const items = ref<Item[]>([])
const counts = ref<Record<string, number>>({})
const selected = ref<Set<number>>(new Set())
const filter = ref('')
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')

const insight = ref('')
const insightLoading = ref(false)
const insightEnabled = ref(true)

const filtering = computed(() =>
  filter.value ? items.value.filter((item) => item.category === filter.value) : items.value,
)
const selectedSize = computed(() =>
  items.value
    .filter((item) => selected.value.has(item.file_id))
    .reduce((sum, item) => sum + (item.file_size || 0), 0),
)
const allFilteredSelected = computed(
  () => filtering.value.length > 0 && filtering.value.every((item) => selected.value.has(item.file_id)),
)

function nameOf(category: string) {
  return CATEGORY_NAMES[category] || category
}

async function analyze() {
  loading.value = true
  error.value = ''
  const res = await window.api.get('/api/cleanup/analyze')
  if (res.ok) {
    const data = res.data as { items?: Item[]; counts?: Record<string, number> }
    items.value = data.items || []
    counts.value = data.counts || {}
    selected.value = new Set()
  } else {
    error.value = res.error || `HTTP ${res.status}`
  }
  loading.value = false
}

async function loadInsight() {
  insightLoading.value = true
  const res = await window.api.get('/api/ai/insights')
  if (res.ok) {
    const data = res.data as { enabled?: boolean; insight?: string | null; error?: string }
    insightEnabled.value = data.enabled !== false
    insight.value = data.insight || data.error || ''
  } else {
    insightEnabled.value = false
  }
  insightLoading.value = false
}

function toggle(item: Item) {
  const next = new Set(selected.value)
  if (next.has(item.file_id)) next.delete(item.file_id)
  else next.add(item.file_id)
  selected.value = next
}

function toggleAll() {
  const next = new Set(selected.value)
  if (allFilteredSelected.value) {
    filtering.value.forEach((item) => next.delete(item.file_id))
  } else {
    filtering.value.forEach((item) => next.add(item.file_id))
  }
  selected.value = next
}

async function execute() {
  const ids = [...selected.value]
  if (!ids.length) return
  const ok = await window.api.confirm(
    `把 ${ids.length} 个文件移入回收区？`,
    `共 ${formatBytes(selectedSize.value)}。可在「历史 → 回收区」恢复。`,
  )
  if (!ok) return
  busy.value = true
  const res = await window.api.post('/api/cleanup/execute', {
    file_ids: ids,
    confirm: true,
  })
  busy.value = false
  if (res.ok) {
    const data = res.data as { removed?: number; freed_size?: number }
    notice.value = `已清理 ${data.removed ?? ids.length} 个文件，释放 ${formatBytes(data.freed_size ?? selectedSize.value)}`
    await analyze()
  } else {
    error.value = res.error || '清理失败'
  }
}

onMounted(() => {
  void analyze()
  void loadInsight()
})
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <h1>清理中心</h1>
        <p>按规则找出可清理项，确认后移入回收区</p>
      </div>
      <div class="head-actions">
        <AppButton :disabled="loading" @click="analyze">{{ loading ? '分析中…' : '重新分析' }}</AppButton>
        <AppButton variant="primary" :disabled="busy || !selected.size" @click="execute">
          清理 {{ selected.size }} 项（{{ formatBytes(selectedSize) }}）
        </AppButton>
      </div>
    </header>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="notice" class="notice">{{ notice }}</p>

    <Panel v-if="insight || insightLoading" title="AI 洞察" hint="基于索引统计生成">
      <p v-if="insightLoading" class="dim">生成中…</p>
      <div v-else class="md" data-cleanup-insight v-html="renderMarkdown(insight)" />
      <p v-if="!insightEnabled" class="dim">未配置 AI 模型，洞察不可用。</p>
    </Panel>

    <Panel title="可清理项" :hint="`共 ${items.length} 项`">
      <div class="toolbar">
        <button
          v-for="(count, category) in counts"
          v-show="category !== 'all'"
          :key="category"
          class="chip"
          :class="{ on: filter === category }"
          @click="filter = filter === category ? '' : String(category)"
        >
          {{ nameOf(String(category)) }} {{ count }}
        </button>
        <span class="spacer" />
        <AppButton size="sm" variant="ghost" :disabled="!filtering.length" @click="toggleAll">
          {{ allFilteredSelected ? '取消全选' : '全选当前' }}
        </AppButton>
      </div>

      <ul v-if="filtering.length" class="list">
        <li v-for="item in filtering" :key="item.file_id" @click="toggle(item)">
          <span class="box" :class="{ on: selected.has(item.file_id) }" />
          <span class="name" :title="item.file_path">{{ item.file_name }}</span>
          <span class="cat">{{ nameOf(item.category) }}</span>
          <span class="reason">{{ item.reason }}</span>
          <span class="size">{{ formatBytes(item.file_size) }}</span>
        </li>
      </ul>
      <p v-else-if="!loading" class="empty">没有需要清理的文件</p>
    </Panel>
  </div>
</template>

<style scoped>
.page { display: flex; flex-direction: column; gap: var(--space-3); max-width: 1000px; }
.page-head { display: flex; align-items: flex-end; justify-content: space-between; }
h1 { margin: 0; font-size: 20px; }
.page-head p { margin: 2px 0 0; color: var(--dim); font-size: 12px; }
.head-actions { display: flex; gap: var(--space-2); }

.toolbar { display: flex; align-items: center; gap: var(--space-2); margin-bottom: var(--space-3); flex-wrap: wrap; }
.spacer { flex: 1; }
.chip {
  padding: 3px 10px;
  color: var(--muted);
  background: var(--bg);
  border: 1px solid var(--line);
  border-radius: 999px;
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
}
.chip:hover { color: var(--text); }
.chip.on { color: #fff; background: var(--primary); border-color: var(--primary); }

.list { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; max-height: 420px; overflow-y: auto; }
.list li {
  display: grid;
  grid-template-columns: 16px minmax(160px, 1.2fr) 88px minmax(120px, 1.4fr) 88px;
  align-items: center;
  gap: var(--space-3);
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  cursor: pointer;
}
.list li:hover { background: #202537; }
.box { width: 13px; height: 13px; border: 1px solid var(--line); border-radius: 3px; }
.box.on { background: var(--primary); border-color: var(--primary); }
.name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cat { color: var(--muted); font-size: 12px; }
.reason { color: var(--dim); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.size { color: var(--muted); font-size: 12px; text-align: right; font-variant-numeric: tabular-nums; }

.dim { color: var(--dim); font-size: 12px; margin: 0; }
.error { margin: 0; padding: 10px 12px; color: #fecaca; background: #3f1d1d; border-radius: var(--radius-sm); }
.notice { margin: 0; padding: 10px 12px; color: #bbf7d0; background: #14321f; border-radius: var(--radius-sm); }
.empty { margin: 0; color: var(--dim); font-size: 13px; }
</style>
