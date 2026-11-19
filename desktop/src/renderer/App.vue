<script setup lang="ts">
import { ref } from 'vue'
import DashboardPage from './pages/DashboardPage.vue'
import FilesPage from './pages/FilesPage.vue'
import Styleguide from './pages/Styleguide.vue'

const TABS = [
  { key: 'dashboard', label: '仪表盘' },
  { key: 'files', label: '文件' },
  { key: 'styleguide', label: '组件' },
] as const

const tab = ref<(typeof TABS)[number]['key']>('dashboard')
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <span class="brand">FileNest</span>
      <nav>
        <button
          v-for="item in TABS"
          :key="item.key"
          :data-tab="item.key"
          :class="{ on: tab === item.key }"
          @click="tab = item.key"
        >{{ item.label }}</button>
      </nav>
    </header>
    <main class="content">
      <DashboardPage v-show="tab === 'dashboard'" />
      <FilesPage v-show="tab === 'files'" />
      <Styleguide v-show="tab === 'styleguide'" />
    </main>
  </div>
</template>

<style scoped>
.shell { min-height: 100vh; display: flex; flex-direction: column; }
.topbar {
  display: flex;
  align-items: center;
  gap: var(--space-5);
  height: 52px;
  padding: 0 var(--space-5);
  border-bottom: 1px solid var(--line);
  background: var(--bg-elev);
}
.brand { font-size: 15px; font-weight: 700; letter-spacing: .02em; }
nav { display: flex; gap: var(--space-1); }
nav button {
  padding: 5px 12px;
  color: var(--muted);
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  font-size: 13px;
  cursor: pointer;
  transition: color 120ms var(--ease), background 120ms var(--ease);
}
nav button:hover { color: var(--text); background: #1c2133; }
nav button.on { color: var(--text); background: #232a41; }
.content { padding: var(--space-5); }
</style>
