<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import BarList from '../components/BarList.vue'
import Panel from '../components/Panel.vue'
import StatCard from '../components/StatCard.vue'
import { formatBytes, formatCount, formatTime, opName } from '../lib/format'

const PALETTE = ['#cba6f7', '#89b4fa', '#a6e3a1', '#f9e2af', '#f38ba8', '#94e2d5', '#fab387']

const data = ref<Record<string, any> | null>(null)
const error = ref('')
const loading = ref(true)

async function load() {
  loading.value = true
  error.value = ''
  const res = await window.api.get('/api/dashboard')
  if (res.ok) {
    data.value = res.data as Record<string, any>
  } else {
    error.value = res.error || `HTTP ${res.status}`
  }
  loading.value = false
}

const typeItems = computed(() =>
  ((data.value?.type_stats as any[]) || []).slice(0, 7).map((row, index) => ({
    label: (data.value?.type_names as Record<string, string>)?.[row.file_type] || row.file_type,
    value: row.count,
    sub: `${formatCount(row.count)} · ${formatBytes(row.total_size)}`,
    color: PALETTE[index % PALETTE.length],
  })),
)

const activities = computed(() => (data.value?.activities as any[]) || [])

onMounted(load)
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <h1>仪表盘</h1>
        <p>本地文件索引概览</p>
      </div>
      <button class="ghost" :disabled="loading" @click="load">
        {{ loading ? '加载中…' : '刷新' }}
      </button>
    </header>

    <p v-if="error" class="error">加载失败：{{ error }}</p>

    <div class="stats">
      <StatCard label="总文件数" :value="formatCount(data?.active_count)" :sub="`近 7 天新增 ${formatCount(data?.recent_7d)}`" />
      <StatCard label="已分类" :value="formatCount(data?.classified_count)" :sub="`覆盖率 ${data?.coverage ?? 0}%`" accent="var(--ok)" />
      <StatCard label="标签数" :value="formatCount(data?.tag_count)" :sub="`关联 ${formatCount(data?.tag_hits)} 次`" accent="var(--warn)" />
      <StatCard label="存储用量" :value="formatBytes(data?.total_size)" :sub="`回收区 ${formatCount(data?.deleted_count)} 项`" accent="var(--purple)" />
    </div>

    <div class="grid">
      <Panel title="文件类型分布" hint="按类型统计">
        <BarList v-if="typeItems.length" :items="typeItems" />
        <p v-else class="empty">还没有扫描数据</p>
      </Panel>

      <Panel title="最近活动" hint="操作历史">
        <ul v-if="activities.length" class="events">
          <li v-for="(item, index) in activities" :key="index">
            <span class="dot" />
            <span class="op">{{ opName(item.operation_type) }}</span>
            <span class="time">{{ formatTime(item.operation_time) }}</span>
          </li>
        </ul>
        <p v-else class="empty">暂无操作记录</p>
      </Panel>
    </div>

    <Panel title="待处理">
      <div class="todo">
        <div><b>{{ formatCount(data?.unclassified_count) }}</b><span>未分类</span></div>
        <div><b>{{ formatCount(data?.duplicate_groups) }}</b><span>重复文件组</span></div>
        <div><b>{{ formatBytes(data?.duplicate_wasted) }}</b><span>重复占用</span></div>
        <div><b>{{ formatCount(data?.saved_queries) }}</b><span>智能集合</span></div>
      </div>
    </Panel>
  </div>
</template>

<style scoped>
.page { display: flex; flex-direction: column; gap: var(--space-4); }
.page-head { display: flex; align-items: flex-end; justify-content: space-between; }
h1 { margin: 0; font-size: 20px; }
.page-head p { margin: 2px 0 0; color: var(--dim); font-size: 12px; }
.ghost {
  padding: 6px 14px;
  color: var(--text);
  background: transparent;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  cursor: pointer;
}
.ghost:hover:not(:disabled) { border-color: var(--primary); }
.ghost:disabled { color: var(--dim); cursor: default; }
.stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--space-4); }
.grid { display: grid; grid-template-columns: 1.3fr 1fr; gap: var(--space-4); }
.empty { margin: 0; color: var(--dim); font-size: 13px; }
.error { margin: 0; padding: 10px 12px; color: #fecaca; background: #3f1d1d; border-radius: var(--radius-sm); }
.events { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
.events li { display: grid; grid-template-columns: 8px 1fr auto; align-items: center; gap: var(--space-3); }
.dot { width: 6px; height: 6px; border-radius: 50%; background: var(--primary); }
.op { font-size: 13px; }
.time { color: var(--dim); font-size: 12px; font-variant-numeric: tabular-nums; }
.todo { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--space-3); }
.todo div { display: flex; flex-direction: column; gap: 2px; }
.todo b { font-size: 18px; font-variant-numeric: tabular-nums; }
.todo span { color: var(--dim); font-size: 12px; }
</style>
