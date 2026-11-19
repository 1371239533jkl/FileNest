<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import AppButton from '../components/AppButton.vue'
import DataTable, { type Column } from '../components/DataTable.vue'
import Panel from '../components/Panel.vue'
import { formatCount } from '../lib/format'

interface Rule {
  id: number
  rule_name: string
  rule_type: string
  rule_pattern: string
  target_category: string
  priority: number
  is_enabled: number
}

const RULE_COLUMNS: Column[] = [
  { key: 'rule_name', title: '名称', width: 'minmax(90px, 1.2fr)' },
  { key: 'rule_type', title: '类型', width: '76px' },
  { key: 'rule_pattern', title: '匹配', width: 'minmax(90px, 1.4fr)' },
  { key: 'target_category', title: '归到', width: '90px' },
  { key: 'priority', title: '优先级', width: '60px', align: 'right' },
  { key: 'is_enabled', title: '状态', width: '64px' },
  { key: 'actions', title: '', width: '88px', align: 'right' },
]

const types = ref<Record<string, { value: string; count: number }[]>>({})
const rules = ref<Rule[]>([])
const classified = ref(0)
const active = ref(0)
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')

const running = ref(false)
const percent = ref(0)
const taskId = ref<number | null>(null)
let timer: ReturnType<typeof setTimeout> | null = null

const form = ref({
  rule_name: '',
  rule_type: 'extension',
  rule_pattern: '',
  target_category: '',
  priority: 0,
})

const coverage = computed(() =>
  active.value ? Math.round((classified.value / active.value) * 1000) / 10 : 0,
)
const typeRows = computed(() =>
  Object.entries(types.value).map(([type, values]) => ({
    type,
    total: values.reduce((sum, item) => sum + item.count, 0),
    values: values.slice(0, 6),
  })),
)

async function load() {
  loading.value = true
  const res = await window.api.get('/api/classification')
  if (res.ok) {
    const data = res.data as { types?: Record<string, any[]>; rules?: Rule[] }
    types.value = (data.types || {}) as Record<string, { value: string; count: number }[]>
    rules.value = data.rules || []
    error.value = ''
  } else {
    error.value = res.error || `HTTP ${res.status}`
  }
  loading.value = false

  const dash = await window.api.get('/api/dashboard')
  if (dash.ok) {
    const data = dash.data as { classified_count?: number; active_count?: number }
    classified.value = data.classified_count || 0
    active.value = data.active_count || 0
  }
}

async function applyAll() {
  const ok = await window.api.confirm(
    '重新分类全部文件？',
    `将按规则重算 ${formatCount(active.value)} 个文件的分类，可在进度条处取消。`,
  )
  if (!ok) return
  const res = await window.api.post('/api/classification/apply')
  if (!res.ok) {
    error.value = res.error || '启动失败'
    return
  }
  taskId.value = (res.data as { task_id: number }).task_id
  percent.value = 0
  running.value = true
  void poll()
}

async function poll() {
  const res = await window.api.get('/api/tasks')
  if (res.ok) {
    const snapshot = res.data as { tasks: any[]; running: number }
    const task = snapshot.tasks.find((t) => t.id === taskId.value)
    if (task) percent.value = task.percent || 0
    if (snapshot.running > 0) {
      timer = setTimeout(poll, 500)
      return
    }
  }
  running.value = false
  taskId.value = null
  await load()
}

async function addRule() {
  if (!form.value.rule_name.trim() || !form.value.rule_pattern.trim()) {
    error.value = '规则名称与匹配内容不能为空'
    return
  }
  busy.value = true
  const query = new URLSearchParams({
    rule_name: form.value.rule_name.trim(),
    rule_type: form.value.rule_type,
    rule_pattern: form.value.rule_pattern.trim(),
    target_category: form.value.target_category.trim(),
    priority: String(Number(form.value.priority) || 0),
  })
  const res = await window.api.post(`/api/classification/rules?${query.toString()}`)
  busy.value = false
  if (res.ok) {
    notice.value = `已添加规则：${form.value.rule_name}`
    form.value = { rule_name: '', rule_type: 'extension', rule_pattern: '', target_category: '', priority: 0 }
    await load()
  } else {
    error.value = res.error || '添加失败'
  }
}

async function toggle(rule: Rule) {
  busy.value = true
  const next = rule.is_enabled ? 0 : 1
  const res = await window.api.post(
    `/api/classification/rules/${rule.id}/toggle?enabled=${next === 1}`,
  )
  busy.value = false
  if (res.ok) await load()
  else error.value = res.error || '切换失败'
}

async function removeRule(rule: Rule) {
  const ok = await window.api.confirm(`删除规则「${rule.rule_name}」？`, '已分类的文件不受影响。')
  if (!ok) return
  busy.value = true
  const res = await window.api.del(`/api/classification/rules/${rule.id}`)
  busy.value = false
  if (res.ok) {
    notice.value = `已删除：${rule.rule_name}`
    await load()
  } else {
    error.value = res.error || '删除失败'
  }
}

onMounted(load)
onBeforeUnmount(() => {
  if (timer) clearTimeout(timer)
})
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <h1>分类</h1>
        <p>
          已分类 {{ formatCount(classified) }} / {{ formatCount(active) }}
          <span class="dim">（覆盖 {{ coverage }}%）</span>
        </p>
      </div>
      <AppButton :disabled="running" @click="applyAll">
        {{ running ? `分类中 ${percent}%` : '重新分类' }}
      </AppButton>
    </header>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="notice" class="notice">{{ notice }}</p>

    <div class="split">
      <Panel title="分类分布" hint="按类型归并" class="side">
        <ul v-if="typeRows.length" class="types">
          <li v-for="row in typeRows" :key="row.type">
            <div class="type-head">
              <b>{{ row.type }}</b>
              <span class="dim">{{ formatCount(row.total) }}</span>
            </div>
            <div class="chips">
              <span v-for="item in row.values" :key="item.value" class="chip">
                {{ item.value }} · {{ item.count }}
              </span>
            </div>
          </li>
        </ul>
        <p v-else-if="!loading" class="empty">还没有分类数据。点右上角「重新分类」按规则生成。</p>
      </Panel>

      <div class="main">
        <Panel title="规则">
          <div class="form">
            <input v-model="form.rule_name" class="field name" placeholder="规则名" />
            <select v-model="form.rule_type" class="field narrow">
              <option value="extension">扩展名</option>
              <option value="keyword">关键词</option>
              <option value="regex">正则</option>
            </select>
            <input v-model="form.rule_pattern" class="field grow" placeholder="匹配内容，如 pdf" />
            <input v-model="form.target_category" class="field target" placeholder="归到" />
            <AppButton variant="primary" :disabled="busy" @click="addRule">添加</AppButton>
          </div>

          <DataTable
            class="rules"
            :rows="rules"
            :columns="RULE_COLUMNS"
            :row-height="40"
            empty-text="还没有规则"
          >
            <template #cell-rule_type="{ row }">
              <span class="dim">{{ row.rule_type }}</span>
            </template>
            <template #cell-rule_pattern="{ row }">
              <span class="mono">{{ row.rule_pattern }}</span>
            </template>
            <template #cell-priority="{ row }">
              <span class="dim">{{ row.priority }}</span>
            </template>
            <template #cell-is_enabled="{ row }">
              <span :class="row.is_enabled ? 'on' : 'off'">{{ row.is_enabled ? '启用' : '停用' }}</span>
            </template>
            <template #cell-actions="{ row }">
              <span class="row-actions">
                <AppButton size="sm" variant="ghost" :disabled="busy" @click.stop="toggle(row)">
                  {{ row.is_enabled ? '停用' : '启用' }}
                </AppButton>
                <AppButton size="sm" variant="ghost" :disabled="busy" @click.stop="removeRule(row)">
                  删除
                </AppButton>
              </span>
            </template>
          </DataTable>
        </Panel>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page { display: flex; flex-direction: column; gap: var(--space-3); height: calc(100vh - 52px - var(--space-5) * 2); }
.page-head { display: flex; align-items: flex-end; justify-content: space-between; }
h1 { margin: 0; font-size: 20px; }
.page-head p { margin: 2px 0 0; color: var(--dim); font-size: 12px; }
.dim { color: var(--dim); font-size: 12px; }

.split {
  display: grid;
  /* minmax(0,1fr) 防止网格项被表单的 min-content 撑宽导致右侧溢出 */
  grid-template-columns: 300px minmax(0, 1fr);
  gap: var(--space-4);
  flex: 1;
  min-height: 0;
}
.side { min-height: 0; overflow: auto; }
.main { display: flex; flex-direction: column; min-height: 0; min-width: 0; }
.main :deep(.panel) { display: flex; flex-direction: column; min-height: 0; flex: 1; }
.main :deep(.panel-body) { display: flex; flex-direction: column; min-height: 0; }
.rules { flex: 1; min-height: 0; }

.types { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-3); }
.type-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 4px; }
.type-head b { font-size: 13px; }
.chips { display: flex; flex-wrap: wrap; gap: 4px; }
.chip {
  padding: 2px 8px;
  color: var(--muted);
  background: #12162a;
  border: 1px solid var(--line);
  border-radius: 999px;
  font-size: 11px;
}

.form {
  display: grid;
  grid-template-columns: 120px 88px minmax(120px, 1fr) 96px auto;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}
.field {
  height: 30px;
  padding: 0 8px;
  color: var(--text);
  background: var(--bg);
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  font-family: inherit;
  font-size: 12px;
  outline: none;
}
.field:focus { border-color: var(--primary); }
.grow { flex: 1 1 160px; min-width: 120px; }
.narrow { width: 88px; flex: none; }
.tiny { width: 64px; flex: none; }
.name { width: 120px; flex: none; }
.target { width: 96px; flex: none; }

.mono { color: var(--muted); font-family: var(--mono); font-size: 12px; }
.on { color: var(--ok); font-size: 12px; }
.off { color: var(--dim); font-size: 12px; }
.row-actions { display: flex; gap: var(--space-1); justify-content: flex-end; }
.error { margin: 0; padding: 10px 12px; color: #fecaca; background: #3f1d1d; border-radius: var(--radius-sm); }
.notice { margin: 0; padding: 10px 12px; color: #bbf7d0; background: #14321f; border-radius: var(--radius-sm); }
.empty { margin: 0; color: var(--dim); font-size: 13px; line-height: 1.8; }
</style>
