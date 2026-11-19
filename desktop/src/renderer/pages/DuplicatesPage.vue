<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppButton from '../components/AppButton.vue'
import Panel from '../components/Panel.vue'
import { formatBytes, formatCount, formatTime } from '../lib/format'

interface Group {
  group_id: number
  file_count: number
  single_size: number
  wasted_size: number
}

interface FileRow {
  id: number
  file_name: string
  file_path: string
  file_size: number
  modify_time: string
}

const groups = ref<Group[]>([])
const total = ref(0)
const wasted = ref(0)
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')

const activeId = ref<number | null>(null)
const files = ref<FileRow[]>([])
const keepId = ref<number | null>(null)

const activeGroup = computed(() => groups.value.find((g) => g.group_id === activeId.value) || null)
const removeCount = computed(() => files.value.filter((f) => f.id !== keepId.value).length)
const removeSize = computed(() =>
  files.value.filter((f) => f.id !== keepId.value).reduce((sum, f) => sum + (f.file_size || 0), 0),
)

async function loadGroups() {
  loading.value = true
  const res = await window.api.get('/api/duplicates?page=0&page_size=50')
  if (res.ok) {
    const data = res.data as { items?: Group[]; total?: number; wasted_size?: number }
    groups.value = data.items || []
    total.value = data.total || 0
    wasted.value = data.wasted_size || 0
    error.value = ''
  } else {
    error.value = res.error || `HTTP ${res.status}`
  }
  loading.value = false
}

async function openGroup(group: Group) {
  activeId.value = group.group_id
  files.value = []
  keepId.value = null
  notice.value = ''
  const res = await window.api.get(`/api/duplicates/${group.group_id}`)
  if (!res.ok) {
    error.value = res.error || `HTTP ${res.status}`
    return
  }
  files.value = (res.data as { files?: FileRow[] }).files || []

  const suggestion = await window.api.post(
    `/api/duplicates/${group.group_id}/suggest?strategy=keep_newest`,
  )
  if (suggestion.ok) {
    keepId.value = (suggestion.data as { keep_file_id: number }).keep_file_id
  } else if (files.value.length) {
    keepId.value = files.value[0].id
  }
}

async function clean() {
  const group = activeGroup.value
  if (!group || keepId.value === null) return
  const removeIds = files.value.filter((f) => f.id !== keepId.value).map((f) => f.id)
  if (!removeIds.length) {
    notice.value = '没有需要删除的文件'
    return
  }

  const keepFile = files.value.find((f) => f.id === keepId.value)
  const ok = await window.api.confirm(
    `把 ${removeIds.length} 个重复文件移入回收区？`,
    `保留：${keepFile?.file_path}\n将删除：${formatBytes(removeSize.value)}\n\n文件会进入回收区，可恢复。`,
  )
  if (!ok) return

  busy.value = true
  const res = await window.api.post('/api/duplicates/clean', {
    group_id: group.group_id,
    keep_file_id: keepId.value,
    remove_file_ids: removeIds,
    confirm: true,
  })
  busy.value = false
  if (res.ok) {
    notice.value = (res.data as { message?: string }).message || '已清理'
    activeId.value = null
    files.value = []
    keepId.value = null
    await loadGroups()
  } else {
    error.value = res.error || '清理失败'
  }
}

function openFile(path: string) {
  void window.api.open(path)
}

onMounted(loadGroups)
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <h1>重复文件</h1>
        <p>
          {{ formatCount(total) }} 组 · 可回收 {{ formatBytes(wasted) }}
          <span class="dim">（按浪费空间排序）</span>
        </p>
      </div>
      <AppButton :disabled="loading" @click="loadGroups">重新加载</AppButton>
    </header>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="notice" class="notice">{{ notice }}</p>

    <div class="split">
      <Panel title="重复组" :hint="`${groups.length} 组`" class="list-panel">
        <ul v-if="groups.length" class="groups">
          <li
            v-for="group in groups"
            :key="group.group_id"
            :class="{ on: group.group_id === activeId }"
            @click="openGroup(group)"
          >
            <span class="gid">#{{ group.group_id }}</span>
            <span class="count">{{ group.file_count }} 个文件</span>
            <span class="size">{{ formatBytes(group.wasted_size) }}</span>
          </li>
        </ul>
        <p v-else-if="!loading" class="empty">
          没有发现重复文件。先去<span class="dim">扫描</span>页建立索引，重复检测会在扫描后执行。
        </p>
      </Panel>

      <Panel
        v-if="activeGroup"
        title="组内文件"
        :hint="`保留一个，其余移入回收区`"
        class="detail-panel"
      >
        <template #actions>
          <AppButton
            variant="primary"
            size="sm"
            :disabled="busy || keepId === null"
            @click="clean"
          >
            清理 {{ removeCount }} 个（{{ formatBytes(removeSize) }}）
          </AppButton>
        </template>

        <ul class="files">
          <li
            v-for="file in files"
            :key="file.id"
            :class="{ keep: file.id === keepId }"
            @click="keepId = file.id"
          >
            <span class="radio" :class="{ on: file.id === keepId }" />
            <span class="fname" :title="file.file_path">{{ file.file_name }}</span>
            <span class="meta">{{ formatBytes(file.file_size) }}</span>
            <span class="meta">{{ formatTime(file.modify_time) }}</span>
            <span class="fpath" :title="file.file_path">{{ file.file_path }}</span>
            <AppButton size="sm" variant="ghost" @click.stop="openFile(file.file_path)">打开</AppButton>
          </li>
        </ul>
        <p class="dim hint">点击行设置要保留的文件；默认按“保留最新”预选。</p>
      </Panel>

      <Panel v-else title="组内文件" class="detail-panel">
        <p class="empty">从左侧选择一个重复组</p>
      </Panel>
    </div>
  </div>
</template>

<style scoped>
.page { display: flex; flex-direction: column; gap: var(--space-4); height: calc(100vh - 52px - var(--space-5) * 2); }
.page-head { display: flex; align-items: flex-end; justify-content: space-between; }
h1 { margin: 0; font-size: 20px; }
.page-head p { margin: 2px 0 0; color: var(--dim); font-size: 12px; }
.error { margin: 0; padding: 10px 12px; color: #fecaca; background: #3f1d1d; border-radius: var(--radius-sm); }
.notice { margin: 0; padding: 10px 12px; color: #bbf7d0; background: #14321f; border-radius: var(--radius-sm); }
.dim { color: var(--dim); }

.split { display: grid; grid-template-columns: 320px 1fr; gap: var(--space-4); flex: 1; min-height: 0; }
.list-panel, .detail-panel { min-height: 0; overflow: auto; }

.groups { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
.groups li {
  display: grid;
  grid-template-columns: 52px 1fr auto;
  align-items: center;
  gap: var(--space-2);
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 13px;
}
.groups li:hover { background: #202537; }
.groups li.on { background: #24304d; box-shadow: inset 2px 0 0 var(--primary); }
.gid { color: var(--dim); font-family: var(--mono); font-size: 12px; }
.count { color: var(--muted); }
.size { color: var(--warn); font-variant-numeric: tabular-nums; }

.files { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
.files li {
  display: grid;
  grid-template-columns: 16px minmax(140px, 1.2fr) 76px 118px minmax(120px, 1.6fr) auto;
  align-items: center;
  gap: var(--space-3);
  padding: 7px 8px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  cursor: pointer;
}
.files li:hover { background: #202537; }
.files li.keep { background: #1c2f28; }
.radio {
  width: 12px;
  height: 12px;
  border: 1px solid var(--line);
  border-radius: 50%;
}
.radio.on { border-color: var(--ok); background: var(--ok); box-shadow: inset 0 0 0 2px #1c2f28; }
.fname { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.meta { color: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; }
.fpath { color: var(--dim); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; direction: rtl; text-align: left; }
.hint { margin: var(--space-3) 0 0; font-size: 12px; }
.empty { margin: 0; color: var(--dim); font-size: 13px; line-height: 1.8; }
</style>
