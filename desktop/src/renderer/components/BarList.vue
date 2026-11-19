<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  items: { label: string; value: number; sub?: string; color?: string }[]
}>()

const max = computed(() => Math.max(1, ...props.items.map((i) => i.value)))
</script>

<template>
  <ul class="bars">
    <li v-for="(item, index) in items" :key="item.label">
      <span class="name">{{ item.label }}</span>
      <span class="track">
        <span
          class="fill"
          :style="{
            width: `${Math.max(2, (item.value / max) * 100)}%`,
            background: item.color || 'var(--primary)',
            animationDelay: `${index * 40}ms`,
          }"
        />
      </span>
      <span class="value">{{ item.sub || item.value }}</span>
    </li>
  </ul>
</template>

<style scoped>
.bars { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
.bars li {
  display: grid;
  grid-template-columns: 64px 1fr auto;
  align-items: center;
  gap: var(--space-3);
}
.name { color: var(--muted); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.track { height: 8px; background: #222741; border-radius: 999px; overflow: hidden; }
.fill {
  display: block;
  height: 100%;
  border-radius: 999px;
  transform-origin: left center;
  animation: grow 320ms var(--ease) both;
}
.value { color: var(--dim); font-size: 12px; font-variant-numeric: tabular-nums; }
@keyframes grow { from { transform: scaleX(0); } to { transform: scaleX(1); } }
</style>
