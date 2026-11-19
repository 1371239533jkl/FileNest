<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { formatBytes, formatTime } from '../lib/format'

const ROW = 44
const PAGE = 200

const rows = ref<any[]>([])
const scroller = ref<HTMLElement | null>(null)
const scrollTop = ref(0)
const viewport = ref(600)
const loading = ref(false)
const error = ref('')
// '' = 首页尚未加载；null = 已到末页
const nextCursor = ref<string | null>('')
const menu = ref<{ x: number; y: number; row: any } | null>(null)

const TYPE_COLORS: Record<string, string> = {
  image: '#cba6f7', document: '#89b4fa', code: '#a6e3a1', video: '#f9e2af',
  audio: '#f38ba8', archive: '#fab387', executable: '#94e2d5', font: '#b4befe',
  other: '#6b6b7b',
}
const TYPE_NAMES: Record<string, string> = {
  image: '图片', document: '文档', code: '代码', video: '视频', audio: '音频',
  archive: '压缩包', executable: '可执行', font: '字体', other: '其他',
}

async function loadMore() {
  if (loading.value || nextCursor.value === null) return
  loading.value = true
  // 始终带 cursor：空串=首页，非空=游标位置
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

function onScroll() {
  const el = scroller.value
  if (!el) return
  scrollTop.value = el.scrollTop
  if (el.scrollTop + el.clientHeight > el.scrollHeight - 800) void loadMore()
}

const startIndex = computed(() => Math.max(0, Math.floor(scrollTop.value / ROW) - 6))
const visible = computed(() =>
  rows.value.slice(startIndex.value, startIndex.value + Math.ceil(viewport.value / ROW) + 12),
)

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

function closeMenu() {
  menu.value = null
}

onMounted(() => {
  const el = scroller.value!
  viewport.value = el.clientHeight
  const observer = new ResizeObserver(() => (viewport.value = el.clientHeight))
  observer.observe(el)
  onBeforeUnmount(() => observer.disconnect())
  void loadMore()

  // 供 --shot 模式测量滚动帧时
  ;(window as any).__scrollPerf = async (frames = 120, step = 600) => {
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
      rows: rows.value.length,
      p50: +times[Math.floor(frames * 0.5)].toFixed(2),
      p95: +times[Math.floor(frames * 0.95)].toFixed(2),
      max: +times[frames - 1].toFixed(2),
    }
  }
})
</script>

<template>
  <div class="page" @click="closeMenu">
    <header class="page-head">
      <div>
        <h1>文件</h1>
        <p>已加载 {{ rows.length }} 条{{ nextCursor === null ? '（已到底）' : '' }}</p>
      </div>
    </header>

    <p v-if="error" class="error">加载失败：{{ error }}</p>

    <div class="table">
      <div class="head row">
        <span>名称</span><span>类型</span><span>大小</span><span>修改时间</span><span>路径</span>
      </div>
      <div ref="scroller" class="body" @scroll="onScroll">
        <div class="spacer" :style="{ height: `${rows.length * ROW}px` }">
          <div
            v-for="(row, index) in visible"
            :key="row.id"
            class="row item"
            :style="{ transform: `translateY(${(startIndex + index) * ROW}px)` }"
            @dblclick="window.api.open(row.file_path)"
            @contextmenu="openMenu($event, row)"
          >
            <span class="name">
              <i class="dot" :style="{ background: TYPE_COLORS[row.file_type] || '#6b6b7b' }" />
              {{ row.file_name }}
            </span>
            <span class="type">{{ TYPE_NAMES[row.file_type] || row.file_type }}</span>
            <span class="size">{{ formatBytes(row.file_size) }}</span>
            <span class="time">{{ formatTime(row.modify_time) }}</span>
            <span class="path">{{ row.file_path }}</span>
          </div>
        </div>
        <div v-if="loading" class="loading">加载中…</div>
      </div>
    </div>

    <ul v-if="menu" class="menu" :style="{ left: `${menu.x}px`, top: `${menu.y}px` }" @click.stop>
      <li @click="runAction('open')">打开</li>
      <li @click="runAction('reveal')">在文件夹中显示</li>
      <li @click="runAction('copy')">复制路径</li>
    </ul>
  </div>
</template>

<style scoped>
.page { display: flex; flex-direction: column; gap: var(--space-4); height: calc(100vh - 52px - var(--space-5) * 2); }
.page-head { display: flex; align-items: flex-end; justify-content: space-between; }
h1 { margin: 0; font-size: 20px; }
.page-head p { margin: 2px 0 0; color: var(--dim); font-size: 12px; }
.error { margin: 0; padding: 10px 12px; color: #fecaca; background: #3f1d1d; border-radius: var(--radius-sm); }

.table {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  overflow: hidden;
}
.row {
  display: grid;
  grid-template-columns: minmax(200px, 1.4fr) 72px 88px 132px minmax(180px, 2fr);
  align-items: center;
  gap: var(--space-3);
  padding: 0 var(--space-4);
  height: 44px;
  font-size: 13px;
}
.head {
  height: 38px;
  color: var(--dim);
  font-size: 12px;
  border-bottom: 1px solid var(--line);
  background: var(--bg-elev);
}
.body { position: relative; overflow-y: auto; flex: 1; }
.spacer { position: relative; }
.item {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  border-bottom: 1px solid rgba(42, 47, 69, .55);
  cursor: default;
  will-change: transform;
}
.item:hover { background: #202537; }
.name { display: flex; align-items: center; gap: 8px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dot { width: 6px; height: 6px; border-radius: 50%; flex: none; }
.type, .time { color: var(--muted); font-size: 12px; }
.size { color: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; }
.path { color: var(--dim); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; direction: rtl; text-align: left; }
.loading { position: absolute; bottom: 8px; right: 16px; color: var(--dim); font-size: 12px; }

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
