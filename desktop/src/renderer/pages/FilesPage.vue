<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppButton from '../components/AppButton.vue'
import DataTable, { type Column } from '../components/DataTable.vue'
import { formatBytes, formatTime } from '../lib/format'

const PAGE = 200
const TEXT_EXT = /\.(txt|md|log|json|csv|py|js|ts|vue|ya?ml|ini|cfg|toml|sql|html|css|sh)$/i

const COLUMNS: Column[] = [
  { key: 'file_name', title: '名称', width: 'minmax(200px, 1.4fr)' },
  { key: 'file_type', title: '类型', width: '72px' },
  { key: 'file_size', title: '大小', width: '88px', align: 'right' },
  { key: 'modify_time', title: '修改时间', width: '132px' },
  { key: 'file_path', title: '路径', width: 'minmax(160px, 1.6fr)' },
]

const TYPE_COLORS: Record<string, string> = {
  image: '#cba6f7', document: '#89b4fa', code: '#a6e3a1', video: '#f9e2af',
  audio: '#f38ba8', archive: '#fab387', executable: '#94e2d5', font: '#b4befe',
  other: '#6b6b7b',
}
const TYPE_NAMES: Record<string, string> = {
  image: '图片', document: '文档', code: '代码', video: '视频', audio: '音频',
  archive: '压缩包', executable: '可执行', font: '字体', other: '其他',
}
const TYPE_OPTIONS = Object.entries(TYPE_NAMES)

const rows = ref<any[]>([])
const loading = ref(false)
const error = ref('')
const nextCursor = ref<string | null>('')
const total = ref<number | null>(null)
const page = ref(0)
const menu = ref<{ x: number; y: number; row: any } | null>(null)

const selected = ref<any | null>(null)
const thumb = ref('')
const snippet = ref('')
const note = ref('')

const keyword = ref('')
const scope = ref<'name' | 'content'>('name')
const typeFilter = ref('')
const minKb = ref('')
const maxKb = ref('')
const startDate = ref('')
const endDate = ref('')

const filtered = computed(
  () =>
    !!keyword.value.trim() || !!typeFilter.value || !!minKb.value ||
    !!maxKb.value || !!startDate.value || !!endDate.value,
)

function buildQuery(reset: boolean) {
  if (!filtered.value) {
    return `/api/files?page_size=${PAGE}&cursor=${encodeURIComponent(
      reset ? '' : nextCursor.value || '',
    )}`
  }
  const params = new URLSearchParams({
    page: String(reset ? 0 : page.value),
    page_size: String(PAGE),
  })
  const word = keyword.value.trim()
  if (word) params.set(scope.value === 'content' ? 'content' : 'name', word)
  if (typeFilter.value) params.set('file_type', typeFilter.value)
  if (minKb.value) params.set('min_size', String(Number(minKb.value) * 1024))
  if (maxKb.value) params.set('max_size', String(Number(maxKb.value) * 1024))
  if (startDate.value) params.set('start_date', startDate.value)
  // 让"截止日"包含当天整天
  if (endDate.value) params.set('end_date', `${endDate.value} 23:59:59`)
  return `/api/files?${params.toString()}`
}

async function fetchPage(reset = false) {
  if (loading.value) return
  if (!reset && !filtered.value && nextCursor.value === null) return
  if (!reset && filtered.value && total.value !== null && rows.value.length >= total.value) return

  if (reset) {
    rows.value = []
    page.value = 0
    nextCursor.value = ''
    total.value = null
    error.value = ''
  }

  loading.value = true
  const res = await window.api.get(buildQuery(reset))
  if (res.ok) {
    const data = res.data as {
      items?: any[]
      next_cursor?: string | null
      total?: number | null
    }
    rows.value = rows.value.concat(data.items || [])
    total.value = data.total ?? null
    if (filtered.value) {
      page.value += 1
    } else {
      nextCursor.value = data.next_cursor ?? null
    }
  } else {
    error.value = res.error || `HTTP ${res.status}`
    if (!filtered.value) nextCursor.value = null
  }
  loading.value = false
}

function resetFilters() {
  keyword.value = ''
  scope.value = 'name'
  typeFilter.value = ''
  minKb.value = ''
  maxKb.value = ''
  startDate.value = ''
  endDate.value = ''
  void fetchPage(true)
}

async function selectRow(row: any) {
  selected.value = row
  thumb.value = ''
  snippet.value = ''
  note.value = ''
  if (row.file_type === 'image') {
    const res = await window.api.thumb(row.file_path, 320)
    if (res.ok) thumb.value = String(res.data)
    else note.value = '缩略图生成失败'
  } else if (TEXT_EXT.test(row.file_path)) {
    const res = await window.api.readText(row.file_path)
    if (res.ok) snippet.value = res.data || ''
    else note.value = res.error || '读取失败'
  } else {
    note.value = '该类型暂不支持预览'
  }
}

function openMenu(event: MouseEvent, row: any) {
  event.preventDefault()
  menu.value = { x: event.clientX, y: event.clientY, row }
}

async function runAction(action: 'open' | 'reveal' | 'copy') {
  const row = menu.value?.row
  menu.value = null
  if (!row) return
  if (action === 'open') await window.api.open(row.file_path)
  if (action === 'reveal') await window.api.reveal(row.file_path)
  if (action === 'copy') await window.api.copy(row.file_path)
}

onMounted(() => fetchPage(true))
</script>

<template>
  <div class="page" @click="menu = null">
    <header class="page-head">
      <div>
        <h1>文件</h1>
        <p>
          已加载 {{ rows.length }} 条
          <template v-if="filtered && total !== null"> / 共 {{ total }} 条</template>
          <template v-else-if="nextCursor === null">（已到底）</template>
        </p>
      </div>
    </header>

    <div class="filters">
      <input
        v-model="keyword"
        class="field grow-field"
        placeholder="文件名 / 正文关键词"
        @keyup.enter="fetchPage(true)"
      />
      <select v-model="scope" class="field">
        <option value="name">文件名</option>
        <option value="content">正文</option>
      </select>
      <select v-model="typeFilter" class="field">
        <option value="">全部类型</option>
        <option v-for="[value, label] in TYPE_OPTIONS" :key="value" :value="value">
          {{ label }}
        </option>
      </select>
      <input v-model="minKb" class="field size" type="number" min="0" placeholder="最小 KB" />
      <input v-model="maxKb" class="field size" type="number" min="0" placeholder="最大 KB" />
      <input v-model="startDate" class="field date" type="date" />
      <input v-model="endDate" class="field date" type="date" />
      <AppButton variant="primary" :disabled="loading" @click="fetchPage(true)">查询</AppButton>
      <AppButton variant="ghost" :disabled="loading" @click="resetFilters">重置</AppButton>
    </div>

    <p v-if="error" class="error">加载失败：{{ error }}</p>

    <div class="split">
      <DataTable
        class="grow"
        :rows="rows"
        :columns="COLUMNS"
        :loading="loading"
        :active-key="selected?.id ?? null"
        perf
        :empty-text="filtered ? '没有符合条件的文件' : '还没有扫描数据，先在扫描页建个索引'"
        @row-click="selectRow"
        @scroll-near-end="fetchPage()"
        @row-dblclick="(row) => window.api.open(row.file_path)"
        @row-contextmenu="({ event, row }) => openMenu(event, row)"
      >
        <template #cell-file_name="{ row }">
          <span class="name">
            <i class="dot" :style="{ background: TYPE_COLORS[row.file_type] || '#6b6b7b' }" />
            {{ row.file_name }}
          </span>
        </template>
        <template #cell-file_type="{ row }">
          <span class="muted">{{ TYPE_NAMES[row.file_type] || row.file_type }}</span>
        </template>
        <template #cell-file_size="{ row }">
          <span class="muted">{{ formatBytes(row.file_size) }}</span>
        </template>
        <template #cell-modify_time="{ row }">
          <span class="muted">{{ formatTime(row.modify_time) }}</span>
        </template>
        <template #cell-file_path="{ row }">
          <span class="path">{{ row.file_path }}</span>
        </template>
      </DataTable>

      <aside class="preview">
        <template v-if="selected">
          <h2 :title="selected.file_name">{{ selected.file_name }}</h2>

          <div class="media">
            <img v-if="thumb" :src="thumb" alt="预览" />
            <pre v-else-if="snippet">{{ snippet }}</pre>
            <p v-else class="note">{{ note || '加载中…' }}</p>
          </div>

          <dl class="meta">
            <dt>类型</dt><dd>{{ TYPE_NAMES[selected.file_type] || selected.file_type }}</dd>
            <dt>大小</dt><dd>{{ formatBytes(selected.file_size) }}</dd>
            <dt>修改</dt><dd>{{ formatTime(selected.modify_time) }}</dd>
            <dt>路径</dt><dd class="path-cell">{{ selected.file_path }}</dd>
          </dl>

          <div class="actions">
            <AppButton size="sm" @click="window.api.open(selected.file_path)">打开</AppButton>
            <AppButton size="sm" variant="ghost" @click="window.api.reveal(selected.file_path)">
              定位
            </AppButton>
          </div>
        </template>
        <p v-else class="note">选中一行查看预览</p>
      </aside>
    </div>

    <ul v-if="menu" class="menu" :style="{ left: `${menu.x}px`, top: `${menu.y}px` }" @click.stop>
      <li @click="runAction('open')">打开</li>
      <li @click="runAction('reveal')">在文件夹中显示</li>
      <li @click="runAction('copy')">复制路径</li>
    </ul>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  height: calc(100vh - 52px - var(--space-5) * 2);
}
.page-head { display: flex; align-items: flex-end; justify-content: space-between; }
h1 { margin: 0; font-size: 20px; }
.page-head p { margin: 2px 0 0; color: var(--dim); font-size: 12px; }
.error { margin: 0; padding: 10px 12px; color: #fecaca; background: #3f1d1d; border-radius: var(--radius-sm); }

.filters { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; }
.field {
  height: 32px;
  padding: 0 10px;
  color: var(--text);
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  font-family: inherit;
  font-size: 13px;
  outline: none;
}
.field:focus { border-color: var(--primary); }
.field::placeholder { color: var(--dim); }
.grow-field { flex: 1; min-width: 200px; }
.size { width: 96px; }
.date { width: 148px; }
select.field { cursor: pointer; }

.split { display: flex; gap: var(--space-4); flex: 1; min-height: 0; }
.grow { flex: 1; min-width: 0; }

.preview {
  width: 280px;
  flex: none;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  overflow: auto;
}
.preview h2 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.media {
  display: grid;
  place-items: center;
  min-height: 120px;
  max-height: 220px;
  background: #12162a;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  overflow: auto;
}
.media img { max-width: 100%; max-height: 218px; display: block; }
.media pre {
  margin: 0;
  padding: 10px;
  width: 100%;
  font-family: var(--mono);
  font-size: 11px;
  line-height: 1.5;
  color: var(--muted);
  white-space: pre-wrap;
  word-break: break-all;
}
.note { margin: 0; color: var(--dim); font-size: 12px; }
.meta { display: grid; grid-template-columns: 40px 1fr; gap: 4px var(--space-2); margin: 0; font-size: 12px; }
.meta dt { color: var(--dim); }
.meta dd { margin: 0; color: var(--muted); overflow: hidden; text-overflow: ellipsis; }
.path-cell { word-break: break-all; }
.actions { display: flex; gap: var(--space-2); margin-top: auto; }

.name { display: flex; align-items: center; gap: 8px; }
.dot { width: 6px; height: 6px; border-radius: 50%; flex: none; }
.muted { color: var(--muted); font-size: 12px; }
.path { color: var(--dim); font-size: 12px; }

.menu {
  position: fixed;
  z-index: 20;
  margin: 0;
  padding: 4px;
  list-style: none;
  min-width: 168px;
  background: #1f2437;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  box-shadow: 0 10px 28px rgba(0, 0, 0, .45);
}
.menu li { padding: 7px 10px; border-radius: 6px; font-size: 13px; cursor: pointer; }
.menu li:hover { background: #2a3048; }
</style>
