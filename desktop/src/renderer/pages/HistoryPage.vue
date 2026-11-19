<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppButton from '../components/AppButton.vue'
import DataTable, { type Column } from '../components/DataTable.vue'
import { formatBytes, formatTime, opName, typeName } from '../lib/format'

const RECYCLE_COLUMNS: Column[] = [
  { key: 'file_name', title: '名称', width: 'minmax(180px, 1.2fr)' },
  { key: 'file_type', title: '类型', width: '72px' },
  { key: 'file_size', title: '大小', width: '88px', align: 'right' },
  { key: 'modify_time', title: '修改时间', width: '132px' },
  { key: 'file_path', title: '原路径', width: 'minmax(160px, 1.6fr)' },
  { key: 'actions', title: '', width: '88px', align: 'right' },
]

const HISTORY_COLUMNS: Column[] = [
  { key: 'operation_time', title: '时间', width: '140px' },
  { key: 'operation_type', title: '操作', width: '88px' },
  { key: 'change', title: '变化', width: 'minmax(200px, 2fr)' },
  { key: 'operation_status', title: '状态', width: '88px' },
  { key: 'actions', title: '', width: '88px', align: 'right' },
]

const view = ref<'recycle' | 'history'>('recycle')
const recycleRows = ref<any[]>([])
const historyRows = ref<any[]>([])
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const opFilter = ref('')

const opTypes = computed(() => [...new Set(historyRows.value.map((r) => r.operation_type))])
const filteredHistory = computed(() =>
  opFilter.value ? historyRows.value.filter((r) => r.operation_type === opFilter.value) : historyRows.value,
)

async function loadRecycle() {
  loading.value = true
  const res = await window.api.get('/api/recycle?page=0&page_size=200')
  if (res.ok) {
    recycleRows.value = (res.data as { items?: any[] }).items || []
    error.value = ''
  } else {
    error.value = res.error || `HTTP ${res.status}`
  }
  loading.value = false
}

async function loadHistory() {
  loading.value = true
  const res = await window.api.get('/api/history?limit=200')
  if (res.ok) {
    historyRows.value = (res.data as { items?: any[] }).items || []
    error.value = ''
  } else {
    error.value = res.error || `HTTP ${res.status}`
  }
  loading.value = false
}

function switchView(next: 'recycle' | 'history') {
  view.value = next
  notice.value = ''
  void (next === 'recycle' ? loadRecycle() : loadHistory())
}

async function restore(row: any) {
  busy.value = true
  const res = await window.api.post(`/api/files/${row.id}/restore`, {
    conflict_strategy: 'rename',
  })
  busy.value = false
  if (res.ok) {
    notice.value = `已恢复：${(res.data as { path?: string }).path || row.file_name}`
    await loadRecycle()
  } else {
    error.value = res.error || '恢复失败'
  }
}

async function undo(row: any) {
  const ok = await window.api.confirm(
    `撤销「${opName(row.operation_type)}」操作？`,
    `${row.old_value || ''} → ${row.new_value || ''}\n\n撤销会尝试把文件恢复到操作前的状态。`,
  )
  if (!ok) return
  busy.value = true
  const res = await window.api.post(`/api/history/${row.id}/undo`)
  busy.value = false
  if (res.ok) {
    notice.value = '已撤销'
    await loadHistory()
  } else {
    error.value = res.error || '撤销失败'
  }
}

onMounted(loadRecycle)
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <h1>历史</h1>
        <p>回收区与操作记录，删除的文件可恢复</p>
      </div>
      <div class="head-actions">
        <AppButton :disabled="busy" @click="view === 'recycle' ? loadRecycle() : loadHistory()">
          刷新
        </AppButton>
      </div>
    </header>

    <div class="segments">
      <button data-seg="recycle" :class="{ on: view === 'recycle' }" @click="switchView('recycle')">
        回收区 {{ recycleRows.length ? `(${recycleRows.length})` : '' }}
      </button>
      <button data-seg="ops" :class="{ on: view === 'history' }" @click="switchView('history')">
        操作记录
      </button>

      <select v-if="view === 'history'" v-model="opFilter" class="field">
        <option value="">全部操作</option>
        <option v-for="type in opTypes" :key="type" :value="type">{{ opName(type) }}</option>
      </select>
    </div>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="notice" class="notice">{{ notice }}</p>

    <DataTable
      v-if="view === 'recycle'"
      class="grow"
      :rows="recycleRows"
      :columns="RECYCLE_COLUMNS"
      :loading="loading"
      empty-text="回收区是空的。删除或去重清理的文件会先到这里。"
    >
      <template #cell-file_type="{ row }">
        <span class="muted">{{ typeName(row.file_type) }}</span>
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
      <template #cell-actions="{ row }">
        <AppButton size="sm" variant="ghost" :disabled="busy" @click.stop="restore(row)">
          恢复
        </AppButton>
      </template>
    </DataTable>

    <DataTable
      v-else
      class="grow"
      :rows="filteredHistory"
      :columns="HISTORY_COLUMNS"
      :loading="loading"
      empty-text="还没有操作记录"
    >
      <template #cell-operation_time="{ row }">
        <span class="muted">{{ formatTime(row.operation_time) }}</span>
      </template>
      <template #cell-operation_type="{ row }">
        <span>{{ opName(row.operation_type) }}</span>
      </template>
      <template #cell-change="{ row }">
        <span class="path">
          {{ row.old_value || '—' }}<span v-if="row.new_value"> → {{ row.new_value }}</span>
        </span>
      </template>
      <template #cell-operation_status="{ row }">
        <span :class="row.operation_status === 'completed' ? 'ok' : 'muted'">
          {{ row.operation_status === 'completed' ? '成功' : row.operation_status }}
        </span>
      </template>
      <template #cell-actions="{ row }">
        <AppButton
          v-if="row.undo_available"
          size="sm"
          variant="ghost"
          :disabled="busy"
          @click.stop="undo(row)"
        >撤销</AppButton>
      </template>
    </DataTable>
  </div>
</template>

<style scoped>
.page { display: flex; flex-direction: column; gap: var(--space-3); height: calc(100vh - 52px - var(--space-5) * 2); }
.page-head { display: flex; align-items: flex-end; justify-content: space-between; }
h1 { margin: 0; font-size: 20px; }
.page-head p { margin: 2px 0 0; color: var(--dim); font-size: 12px; }
.head-actions { display: flex; gap: var(--space-2); }

.segments { display: flex; align-items: center; gap: var(--space-2); }
.segments button {
  padding: 5px 12px;
  color: var(--muted);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
}
.segments button:hover { color: var(--text); background: #1c2133; }
.segments button.on { color: var(--text); background: #232a41; border-color: var(--line); }
.field {
  height: 30px;
  padding: 0 8px;
  color: var(--text);
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  font-family: inherit;
  font-size: 12px;
  outline: none;
}
.grow { flex: 1; min-height: 0; }
.error { margin: 0; padding: 10px 12px; color: #fecaca; background: #3f1d1d; border-radius: var(--radius-sm); }
.notice { margin: 0; padding: 10px 12px; color: #bbf7d0; background: #14321f; border-radius: var(--radius-sm); }
.muted { color: var(--muted); font-size: 12px; }
.path { color: var(--dim); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ok { color: var(--ok); font-size: 12px; }
</style>
