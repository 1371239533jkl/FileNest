<script setup lang="ts">
defineProps<{ title?: string; hint?: string }>()
</script>

<template>
  <section class="panel">
    <header v-if="title" class="panel-head">
      <h2>{{ title }}</h2>
      <span v-if="hint" class="hint">{{ hint }}</span>
      <slot name="actions" />
    </header>
    <div class="panel-body">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.panel {
  display: flex;
  flex-direction: column;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  overflow: hidden;
}
.panel-head {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--line);
}
.panel-head h2 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: .02em;
}
.hint { color: var(--dim); font-size: 12px; }
.panel-body { padding: var(--space-4); flex: 1; }
</style>
