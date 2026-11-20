<script setup lang="ts">
import { computed, ref } from 'vue'
import ChatPage from './pages/ChatPage.vue'
import ClassificationPage from './pages/ClassificationPage.vue'
import CleanupPage from './pages/CleanupPage.vue'
import DashboardPage from './pages/DashboardPage.vue'
import DuplicatesPage from './pages/DuplicatesPage.vue'
import FilesPage from './pages/FilesPage.vue'
import HistoryPage from './pages/HistoryPage.vue'
import ScanPage from './pages/ScanPage.vue'
import SettingsPage from './pages/SettingsPage.vue'
import Styleguide from './pages/Styleguide.vue'
import TagsPage from './pages/TagsPage.vue'
import TimelinePage from './pages/TimelinePage.vue'

interface Tab {
  key: string
  label: string
  dev?: boolean
}

// 分组导航：目的地在侧栏按职责归档，避免顶部一行塞 12 项
const SECTIONS: { title: string; items: Tab[] }[] = [
  { title: '', items: [{ key: 'dashboard', label: '仪表盘' }] },
  {
    title: '文件',
    items: [
      { key: 'files', label: '文件' },
      { key: 'duplicates', label: '重复' },
      { key: 'classification', label: '分类' },
      { key: 'cleanup', label: '清理' },
    ],
  },
  {
    title: '智能',
    items: [
      { key: 'chat', label: 'AI 对话' },
      { key: 'tags', label: '标签' },
    ],
  },
  {
    title: '记录',
    items: [
      { key: 'history', label: '历史' },
      { key: 'timeline', label: '时间线' },
    ],
  },
  {
    title: '系统',
    items: [
      { key: 'scan', label: '扫描' },
      { key: 'settings', label: '设置' },
      { key: 'styleguide', label: '组件', dev: true },
    ],
  },
]

const sections = computed(() =>
  SECTIONS.map((section) => ({
    ...section,
    // 组件总览只在开发构建里出现，发布版自动隐藏
    items: section.items.filter((item) => !item.dev || import.meta.env.DEV),
  })).filter((section) => section.items.length > 0),
)

const tab = ref('dashboard')
</script>

<template>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand">FileNest</div>
      <nav>
        <section v-for="section in sections" :key="section.title || 'root'">
          <h3 v-if="section.title">{{ section.title }}</h3>
          <button
            v-for="item in section.items"
            :key="item.key"
            :data-tab="item.key"
            :class="{ on: tab === item.key }"
            @click="tab = item.key"
          >{{ item.label }}</button>
        </section>
      </nav>
    </aside>

    <main class="content">
      <DashboardPage v-show="tab === 'dashboard'" />
      <FilesPage v-show="tab === 'files'" />
      <ChatPage v-show="tab === 'chat'" />
      <DuplicatesPage v-show="tab === 'duplicates'" />
      <ClassificationPage v-show="tab === 'classification'" />
      <CleanupPage v-show="tab === 'cleanup'" />
      <TagsPage v-show="tab === 'tags'" />
      <ScanPage v-show="tab === 'scan'" />
      <HistoryPage v-show="tab === 'history'" />
      <TimelinePage v-show="tab === 'timeline'" />
      <SettingsPage v-show="tab === 'settings'" />
      <Styleguide v-show="tab === 'styleguide'" />
    </main>
  </div>
</template>

<style scoped>
.shell { display: flex; min-height: 100vh; }

.sidebar {
  width: 176px;
  flex: none;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  padding: var(--space-4) var(--space-3);
  border-right: 1px solid var(--line);
  background: var(--bg-elev);
}
.brand { padding: 0 var(--space-2); font-size: 15px; font-weight: 700; letter-spacing: .02em; }
nav { display: flex; flex-direction: column; gap: var(--space-4); }
nav section { display: flex; flex-direction: column; gap: 2px; }
nav h3 {
  margin: 0 0 2px;
  padding: 0 var(--space-2);
  color: var(--dim);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: .08em;
}
nav button {
  padding: 6px var(--space-2);
  color: var(--muted);
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  font-family: inherit;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  transition: color 120ms var(--ease), background 120ms var(--ease);
}
nav button:hover { color: var(--text); background: #1c2133; }
nav button.on { color: var(--text); background: #232a41; box-shadow: inset 2px 0 0 var(--primary); }

.content { flex: 1; min-width: 0; padding: var(--space-5); }
</style>
