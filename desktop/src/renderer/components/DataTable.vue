<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

export interface Column {
  key: string
  title: string
  width?: string
  align?: 'left' | 'right'
}

const props = withDefaults(
  defineProps<{
    rows: any[]
    columns: Column[]
    rowKey?: string
    rowHeight?: number
    loading?: boolean
    emptyText?: string
    perf?: boolean
  }>(),
  { rowKey: 'id', rowHeight: 44, loading: false, emptyText: '暂无数据', perf: false },
)

const emit = defineEmits<{
  (e: 'row-dblclick', row: any): void
  (e: 'row-contextmenu', payload: { event: MouseEvent; row: any }): void
  (e: 'scroll-near-end'): void
}>()

const scroller = ref<HTMLElement | null>(null)
const scrollTop = ref(0)
const viewport = ref(600)
let observer: ResizeObserver | null = null

const template = computed(() =>
  props.columns.map((column) => column.width || '1fr').join(' '),
)
const startIndex = computed(() =>
  Math.max(0, Math.floor(scrollTop.value / props.rowHeight) - 6),
)
const windowSize = computed(() => Math.ceil(viewport.value / props.rowHeight) + 12)
const visible = computed(() =>
  props.rows.slice(startIndex.value, startIndex.value + windowSize.value),
)

function onScroll() {
  const el = scroller.value
  if (!el) return
  scrollTop.value = el.scrollTop
  if (el.scrollTop + el.clientHeight > el.scrollHeight - 800) emit('scroll-near-end')
}

onMounted(() => {
  const el = scroller.value
  if (!el) return
  viewport.value = el.clientHeight
  observer = new ResizeObserver(() => (viewport.value = el.clientHeight))
  observer.observe(el)
})

onBeforeUnmount(() => observer?.disconnect())

// 供 --shot 模式测量滚动帧时；只有主表格注册，避免被示例表格覆盖
onMounted(() => {
  if (!props.perf) return
  ;(window as any).__scrollPerf = async (frames = 120, step = 600) => {
    const el = scroller.value!
    const times: number[] = []
    let last = performance.now()
    for (let i = 0; i < frames; i++) {
      el.scrollTop += step
      await new Promise(requestAnimationFrame)
      const now = performance.now()
      times.push(now - last)
      last = now
    }
    times.sort((a, b) => a - b)
    return {
      rows: props.rows.length,
      p50: +times[Math.floor(frames * 0.5)].toFixed(2),
      p95: +times[Math.floor(frames * 0.95)].toFixed(2),
      max: +times[frames - 1].toFixed(2),
    }
  }
})
</script>

<template>
  <div class="table">
    <div class="head row" :style="{ gridTemplateColumns: template }">
      <span
        v-for="column in columns"
        :key="column.key"
        :style="{ textAlign: column.align || 'left' }"
      >{{ column.title }}</span>
    </div>

    <div ref="scroller" class="body" @scroll="onScroll">
      <div v-if="!rows.length && !loading" class="state">
        <slot name="empty">{{ emptyText }}</slot>
      </div>

      <div v-else class="spacer" :style="{ height: `${rows.length * rowHeight}px` }">
        <div
          v-for="(row, index) in visible"
          :key="row[rowKey]"
          class="row item"
          :style="{
            gridTemplateColumns: template,
            height: `${rowHeight}px`,
            transform: `translateY(${(startIndex + index) * rowHeight}px)`,
          }"
          @dblclick="emit('row-dblclick', row)"
          @contextmenu="emit('row-contextmenu', { event: $event, row })"
        >
          <span
            v-for="column in columns"
            :key="column.key"
            :style="{ textAlign: column.align || 'left' }"
            class="cell"
          >
            <slot :name="`cell-${column.key}`" :row="row" :value="row[column.key]">
              {{ row[column.key] }}
            </slot>
          </span>
        </div>
      </div>

      <div v-if="loading" class="loading">加载中…</div>
    </div>
  </div>
</template>

<style scoped>
.table {
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  overflow: hidden;
}
.row {
  display: grid;
  align-items: center;
  gap: var(--space-3);
  padding: 0 var(--space-4);
  font-size: 13px;
}
.head {
  height: 38px;
  flex: none;
  color: var(--dim);
  font-size: 12px;
  background: var(--bg-elev);
  border-bottom: 1px solid var(--line);
}
.body { position: relative; flex: 1; min-height: 0; overflow-y: auto; }
.spacer { position: relative; }
.item {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  border-bottom: 1px solid rgba(42, 47, 69, .55);
  will-change: transform;
}
.item:hover { background: #202537; }
.cell { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.state {
  display: grid;
  place-items: center;
  height: 100%;
  min-height: 180px;
  color: var(--dim);
  font-size: 13px;
}
.loading { position: absolute; right: 16px; bottom: 8px; color: var(--dim); font-size: 12px; }
</style>
