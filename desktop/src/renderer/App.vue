<script setup lang="ts">
import { onMounted, ref } from 'vue'

const info = ref<SidecarInfo>({ status: 'starting', port: 0 })

async function refresh() {
  info.value = await window.api.health()
}

onMounted(refresh)
</script>

<template>
  <main class="shell">
    <h1>FileNest</h1>
    <p class="sub">Electron + Vue 3 + TypeScript 骨架</p>
    <div class="card" :data-status="info.status">
      <span class="dot"></span>
      <div>
        <strong>Python sidecar: {{ info.status }}</strong>
        <p v-if="info.status === 'ok'">
          v{{ info.version }} · pid {{ info.pid }} · 127.0.0.1:{{ info.port }}
        </p>
        <p v-else-if="info.error">{{ info.error }}</p>
        <p v-else>正在等待 /health 就绪…</p>
      </div>
    </div>
    <button @click="refresh">重新检查</button>
  </main>
</template>

<style>
:root {
  --bg: #0f0f1a;
  --card: #1a1e2e;
  --line: #2a2f45;
  --text: #e8e8ef;
  --muted: #a0a0b0;
  --ok: #10b981;
  --warn: #f59e0b;
  --err: #ef4444;
}
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 14px/1.6 "Microsoft YaHei UI", "PingFang SC", sans-serif;
}
.shell { padding: 32px; max-width: 560px; }
h1 { margin: 0 0 4px; font-size: 22px; }
.sub { margin: 0 0 24px; color: var(--muted); }
.card {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 16px;
}
.card p { margin: 4px 0 0; color: var(--muted); }
.dot {
  width: 8px;
  height: 8px;
  margin-top: 8px;
  border-radius: 50%;
  background: var(--warn);
}
[data-status="ok"] .dot { background: var(--ok); }
[data-status="failed"] .dot { background: var(--err); }
button {
  margin-top: 16px;
  padding: 8px 16px;
  color: var(--text);
  background: transparent;
  border: 1px solid var(--line);
  border-radius: 8px;
  cursor: pointer;
}
button:hover { border-color: #3b82f6; }
</style>
