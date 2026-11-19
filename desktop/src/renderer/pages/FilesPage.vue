<script setup lang="ts">
import { onMounted, ref } from 'vue'
import DataTable, { type Column } from '../components/DataTable.vue'
import { formatBytes, formatTime } from '../lib/format'

const PAGE = 200

const COLUMNS: Column[] = [
  { key: 'file_name', title: '名称', width: 'minmax(200px, 1.4fr)' },
  { key: 'file_type', title: '类型', width: '72px' },
  { key: 'file_size', title: '大小', width: '88px', align: 'right' },
  { key: 'modify_time', title: '修改时间', width: '132px' },
  { key: 'file_path', title: '路径', width: 'minmax(180px, 2fr)' },
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

const rows = ref<any[]>([])
const loading = ref(false)
const error = ref('')
const nextCursor = ref<string | null>('') // '' 首页未加载，null 已到末页
const menu = ref<{ x: number; y: number; row: any } | null>(null)

async function loadMore() {
  if (loading.value || nextCursor.value === null) return
  loading.value = true
  const suffix = `&cursor=${encodeURIComponent(nextCursor.value || '')}`
  const res = await window.api.get(`/api/files?page_size=${PAGE}${suffix}`)
  if (res.ok) {
    const data = res.data as { items?: any[]; next_cursor?: string | null }
    rows.value = rows.value.concat(data.items || [])
    nextCursor.value = data.next_cursor ?? null
  } else {
    error.value = res.error || `HTTP ${res.status}`
    nextCursor.value = null
  }
  loading.value = false
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

onMounted(loadMore)
</script>

<template>
  <div class="page" @click="menu = null">
    <header class="page-head">
      <div>
        <h1>文件</h1>
        <p>已加载 {{ rows.length }} 条{{ nextCursor === null ? '（已到底）' : '' }}</p>
      </div>
    </header>

    <p v-if="error" class="error">加载失败：{{ error }}</p>

    <DataTable
      class="grow"
      :rows="rows"
      :columns="COLUMNS"
      :loading="loading"
      perf
      empty-text="还没有扫描数据，先在扫描页建个索引"
      @scroll-near-end="loadMore"
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
  gap: var(--space-4);
  height: calc(100vh - 52px - var(--space-5) * 2);
}
.grow { flex: 1; min-height: 0; }
.page-head { display: flex; align-items: flex-end; justify-content: space-between; }
h1 { margin: 0; font-size: 20px; }
.page-head p { margin: 2px 0 0; color: var(--dim); font-size: 12px; }
.error { margin: 0; padding: 10px 12px; color: #fecaca; background: #3f1d1d; border-radius: var(--radius-sm); }
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
