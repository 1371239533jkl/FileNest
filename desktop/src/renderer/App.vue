<script setup lang="ts">
import DashboardPage from './pages/DashboardPage.vue'
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <span class="brand">FileNest</span>
      <span class="tag">本地索引</span>
    </header>
    <main class="content">
      <DashboardPage />
    </main>
  </div>
</template>

<style scoped>
.shell { min-height: 100vh; display: flex; flex-direction: column; }
.topbar {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  height: 52px;
  padding: 0 var(--space-5);
  border-bottom: 1px solid var(--line);
  background: var(--bg-elev);
}
.brand { font-size: 15px; font-weight: 700; letter-spacing: .02em; }
.tag {
  padding: 1px 8px;
  color: var(--dim);
  font-size: 11px;
  border: 1px solid var(--line);
  border-radius: 999px;
}
.content { padding: var(--space-5); }
</style>
