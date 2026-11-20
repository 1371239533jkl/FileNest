<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppButton from '../components/AppButton.vue'
import Panel from '../components/Panel.vue'
import { formatCount, formatTime, opName } from '../lib/format'

interface Event {
  event_source: 'operation' | 'external'
  id: number
  event_type: string
  event_time: string
  file_id: number | null
  old_value: string | null
  new_value: string | null
  status: string
  error_message?: string | null
}

const MODES = [
  { key: 'all', label: '全部' },
  { key: 'operations', label: '操作' },
  { key: 'external', label: '外部变更' },
] as const

const events = ref<Event[]>([])
const mode = ref<'all' | 'operations' | 'external'>('all')
const typeFilter = ref('')
const loading = ref(false)
const error = ref('')

const types = computed(() => [...new Set(events.value.map((item) => item.event_type))])
const filtered = computed(() =>
  typeFilter.value
    ? events.value.filter((item) => item.event_type === typeFilter.value)
    : events.value,
)

const grouped = computed(() => {
  const buckets = new Map<string, Event[]>()
  for (const item of filtered.value) {
    const day = (item.event_time || '').slice(0, 10) || '未知日期'
    if (!buckets.has(day)) buckets.set(day, [])
    buckets.get(day)!.push(item)
  }
  return [...buckets.entries()].map(([day, items]) => ({ day, items }))
})

async function load() {
  loading.value = true
  error.value = ''
  const res = await window.api.get(`/api/timeline?mode=${mode.value}&limit=300`)
  if (res.ok) {
    events.value = (res.data as { items?: Event[] }).items || []
  } else {
    error.value = res.error || `HTTP ${res.status}`
  }
  loading.value = false
}

function switchMode(next: 'all' | 'operations' | 'external') {
  mode.value = next
  typeFilter.value = ''
  void load()
}

function label(event: Event) {
  return event.event_source === 'operation' ? opName(event.event_type) : event.event_type
}

onMounted(load)
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <h1>时间线</h1>
        <p>{{ formatCount(filtered.length) }} 条记录，按天归并</p>
      </div>
      <AppButton :disabled="loading" @click="load">刷新</AppButton>
    </header>

    <p v-if="error" class="error">{{ error }}</p>

    <Panel>
      <div class="toolbar">
        <button
          v-for="item in MODES"
          :key="item.key"
          class="chip"
          :class="{ on: mode === item.key }"
          @click="switchMode(item.key)"
        >{{ item.label }}</button>
        <select v-model="typeFilter" class="field">
          <option value="">全部类型</option>
          <option v-for="type in types" :key="type" :value="type">{{ opName(type) }}</option>
        </select>
      </div>

      <div v-if="grouped.length" class="timeline">
        <section v-for="group in grouped" :key="group.day">
          <h2 class="day">{{ group.day }}</h2>
          <ul>
            <li v-for="event in group.items" :key="`${event.event_source}-${event.id}`">
              <span class="dot" :class="event.event_source" />
              <span class="time">{{ formatTime(event.event_time) }}</span>
              <span class="label">{{ label(event) }}</span>
              <span class="change">
                {{ event.old_value || '—' }}
                <span v-if="event.new_value" class="arrow"> → {{ event.new_value }}</span>
              </span>
              <span class="status" :class="{ bad: event.status !== 'completed' && event.status !== 'ok' }">
                {{ event.status === 'completed' || event.status === 'ok' ? '成功' : event.status }}
              </span>
            </li>
          </ul>
        </section>
      </div>
      <p v-else-if="!loading" class="empty">还没有记录。扫描、清理、去重等操作会出现在这里。</p>
    </Panel>
  </div>
</template>

<style scoped>
.page { display: flex; flex-direction: column; gap: var(--space-3); max-width: 1000px; }
.page-head { display: flex; align-items: flex-end; justify-content: space-between; }
h1 { margin: 0; font-size: 20px; }
.page-head p { margin: 2px 0 0; color: var(--dim); font-size: 12px; }

.toolbar { display: flex; align-items: center; gap: var(--space-2); margin-bottom: var(--space-4); }
.chip {
  padding: 3px 12px;
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
.field {
  height: 28px;
  margin-left: auto;
  padding: 0 8px;
  color: var(--text);
  background: var(--bg);
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  font-family: inherit;
  font-size: 12px;
  outline: none;
}

.timeline { display: grid; gap: var(--space-4); }
.day {
  margin: 0 0 var(--space-2);
  color: var(--dim);
  font-size: 12px;
  font-weight: 500;
  letter-spacing: .04em;
}
.timeline ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
.timeline li {
  display: grid;
  grid-template-columns: 8px 132px 78px minmax(160px, 1fr) 64px;
  align-items: center;
  gap: var(--space-3);
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  font-size: 13px;
}
.timeline li:hover { background: #202537; }
.dot { width: 6px; height: 6px; border-radius: 50%; background: var(--primary); }
.dot.external { background: var(--warn); }
.time { color: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; }
.label { font-size: 13px; }
.change { color: var(--dim); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.arrow { color: var(--muted); }
.status { color: var(--ok); font-size: 12px; }
.status.bad { color: var(--warn); }

.error { margin: 0; padding: 10px 12px; color: #fecaca; background: #3f1d1d; border-radius: var(--radius-sm); }
.empty { margin: 0; color: var(--dim); font-size: 13px; }
</style>
