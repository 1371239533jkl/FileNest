<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import AppButton from '../components/AppButton.vue'
import Panel from '../components/Panel.vue'
import { formatCount } from '../lib/format'

interface Task {
  id: number
  name: string
  status: 'running' | 'done' | 'failed' | 'cancelled'
  current: number
  total: number
  percent: number
  error: string
  result?: { scanned: number; written: number; hashed: number; elapsed_s: number } | null
  started_at: number
  finished_at: number
}

const STATUS_TEXT: Record<string, string> = {
  running: '进行中', done: '完成', failed: '失败', cancelled: '已取消',
}
const STATUS_COLOR: Record<string, string> = {
  running: 'var(--primary)', done: 'var(--ok)', failed: 'var(--danger)', cancelled: 'var(--warn)',
}

const directory = ref('')
const recursive = ref(true)
const computeHash = ref(true)
const tasks = ref<Task[]>([])
const activeId = ref<number | null>(null)
const error = ref('')
const starting = ref(false)
let timer: ReturnType<typeof setTimeout> | null = null

const active = computed(() => tasks.value.find((t) => t.id === activeId.value) || null)
const running = computed(() => tasks.value.some((t) => t.status === 'running'))

function stopPolling() {
  if (timer) clearTimeout(timer)
  timer = null
}

async function refresh() {
  const res = await window.api.get('/api/tasks')
  if (res.ok) {
    tasks.value = (res.data as { tasks?: Task[] }).tasks || []
    if (running.value) {
      timer = setTimeout(refresh, 500)
    } else {
      stopPolling()
    }
  }
}

async function pick() {
  const picked = await window.api.pickDirectory()
  if (picked) directory.value = picked
}

async function start() {
  const target = directory.value.trim()
  if (!target) {
    error.value = '请先选择要扫描的目录'
    return
  }
  error.value = ''
  starting.value = true
  const res = await window.api.post('/api/scan/start', {
    directory: target,
    recursive: recursive.value,
    compute_hash: computeHash.value,
  })
  starting.value = false
  if (!res.ok) {
    error.value = res.error || `HTTP ${res.status}`
    return
  }
  activeId.value = (res.data as { task_id: number }).task_id
  stopPolling()
  void refresh()
}

async function cancel() {
  const task = active.value
  if (!task) return
  const res = await window.api.post(`/api/scan/cancel?task_id=${task.id}`)
  if (!res.ok) error.value = res.error || '取消失败'
  void refresh()
}

function duration(task: Task) {
  const end = task.finished_at || Date.now() / 1000
  const seconds = Math.max(0, end - task.started_at)
  return seconds < 60 ? `${seconds.toFixed(1)}s` : `${Math.floor(seconds / 60)}m${Math.round(seconds % 60)}s`
}

onMounted(refresh)
onBeforeUnmount(stopPolling)
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <h1>扫描</h1>
        <p>建立或更新本地文件索引</p>
      </div>
    </header>

    <Panel title="新建扫描" hint="扫描在后台线程执行，可随时取消">
      <div class="form">
        <input
          v-model="directory"
          class="field dir"
          placeholder="粘贴目录路径，或点击“选择目录”"
          @keyup.enter="start"
        />
        <AppButton @click="pick">选择目录</AppButton>
        <label class="check"><input v-model="recursive" type="checkbox" />包含子目录</label>
        <label class="check"><input v-model="computeHash" type="checkbox" />计算文件哈希</label>
        <AppButton variant="primary" :disabled="starting || running" @click="start">
          {{ starting ? '提交中…' : '开始扫描' }}
        </AppButton>
      </div>
      <p v-if="error" class="error">{{ error }}</p>
    </Panel>

    <Panel v-if="active" title="当前任务" :hint="`#${active.id}`">
      <div class="task">
        <div class="task-head">
          <span class="badge" :style="{ color: STATUS_COLOR[active.status] }">
            {{ STATUS_TEXT[active.status] }}
          </span>
          <span class="path">{{ active.name }}</span>
          <span class="muted">{{ active.current }} / {{ active.total || '?' }}</span>
          <AppButton
            v-if="active.status === 'running'"
            size="sm"
            variant="ghost"
            @click="cancel"
          >取消</AppButton>
        </div>

        <div class="bar">
          <span
            class="fill"
            :style="{
              width: `${active.percent}%`,
              background: STATUS_COLOR[active.status],
            }"
          />
        </div>

        <p class="muted">
          {{ active.percent }}%
          <template v-if="active.result">
            · 入库 {{ formatCount(active.result.written) }} 条
            · 哈希 {{ formatCount(active.result.hashed) }} 条
            · 耗时 {{ active.result.elapsed_s }}s
          </template>
          <template v-else-if="active.error"> · {{ active.error }}</template>
        </p>
      </div>
    </Panel>

    <Panel title="最近任务" hint="最多保留 50 条">
      <ul v-if="tasks.length" class="list">
        <li v-for="task in tasks.slice(0, 8)" :key="task.id" @click="activeId = task.id">
          <span class="badge" :style="{ color: STATUS_COLOR[task.status] }">
            {{ STATUS_TEXT[task.status] }}
          </span>
          <span class="path">{{ task.name }}</span>
          <span class="muted">{{ task.percent }}%</span>
          <span class="muted time">{{ duration(task) }}</span>
        </li>
      </ul>
      <p v-else class="muted">还没有扫描任务</p>
    </Panel>
  </div>
</template>

<style scoped>
.page { display: flex; flex-direction: column; gap: var(--space-4); max-width: 960px; }
.page-head h1 { margin: 0; font-size: 20px; }
.page-head p { margin: 2px 0 0; color: var(--dim); font-size: 12px; }

.form { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; }
.field {
  height: 32px;
  padding: 0 10px;
  color: var(--text);
  background: var(--bg);
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  font-family: inherit;
  font-size: 13px;
  outline: none;
}
.field:focus { border-color: var(--primary); }
.dir { flex: 1; min-width: 260px; }
.check {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--muted);
  font-size: 12px;
  cursor: pointer;
}
.check input { accent-color: var(--primary); }
.error { margin: var(--space-2) 0 0; color: #fca5a5; font-size: 12px; }

.task { display: flex; flex-direction: column; gap: var(--space-3); }
.task-head { display: flex; align-items: center; gap: var(--space-3); }
.badge { font-size: 12px; font-weight: 600; }
.bar { height: 6px; background: #222741; border-radius: 999px; overflow: hidden; }
.fill { display: block; height: 100%; border-radius: 999px; transition: width 200ms var(--ease); }
.path { flex: 1; color: var(--muted); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.muted { margin: 0; color: var(--dim); font-size: 12px; font-variant-numeric: tabular-nums; }
.time { width: 56px; text-align: right; }

.list { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
.list li {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  cursor: pointer;
}
.list li:hover { background: #202537; }
</style>
