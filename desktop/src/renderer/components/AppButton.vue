<script setup lang="ts">
withDefaults(
  defineProps<{
    variant?: 'default' | 'primary' | 'ghost'
    size?: 'sm' | 'md'
    disabled?: boolean
  }>(),
  { variant: 'default', size: 'md', disabled: false },
)
</script>

<template>
  <button class="btn" :class="[variant, size]" :disabled="disabled">
    <slot />
  </button>
</template>

<style scoped>
.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--line);
  background: transparent;
  color: var(--text);
  cursor: pointer;
  font-family: inherit;
  transition: background 120ms var(--ease), border-color 120ms var(--ease), color 120ms var(--ease);
}
.md { height: 32px; padding: 0 14px; font-size: 13px; }
.sm { height: 26px; padding: 0 10px; font-size: 12px; }

.default { background: #232a41; border-color: #313a58; }
.default:hover:not(:disabled) { background: #2a3350; }

.primary { background: var(--primary); border-color: var(--primary); color: #fff; }
.primary:hover:not(:disabled) { background: #4b8ef8; }

.ghost { background: transparent; }
.ghost:hover:not(:disabled) { border-color: var(--primary); color: #fff; }

.btn:disabled { color: var(--dim); cursor: default; opacity: .7; }
</style>
