<script setup lang="ts">
defineProps<{
  label: string
  value: string
  sub?: string
  accent?: string
}>()
</script>

<template>
  <div class="stat">
    <span class="label">{{ label }}</span>
    <strong :style="{ color: accent || 'var(--text)' }">{{ value }}</strong>
    <span class="sub">{{ sub || '\u00a0' }}</span>
  </div>
</template>

<style scoped>
.stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--space-4);
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  min-width: 0;
}
.label { color: var(--muted); font-size: 12px; }
strong {
  font-size: 26px;
  line-height: 1.25;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.sub { color: var(--dim); font-size: 12px; }
</style>
