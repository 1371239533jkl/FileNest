<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppButton from '../components/AppButton.vue'
import Panel from '../components/Panel.vue'

interface Provider {
  provider_id: string
  name: string
  base_url: string
  model: string
  models: string
  timeout: number
  api_key: string
  has_key: boolean
  active: boolean
}

interface Template {
  provider_id: string
  name: string
  base_url: string
  models: string
  default_model: string
  timeout: number
}

const providers = ref<Provider[]>([])
const templates = ref<Template[]>([])
const activeId = ref('')
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')

const version = ref('')
const port = ref(0)
const pid = ref(0)

const editing = ref(false)
const form = ref({
  provider_id: '',
  name: '',
  base_url: '',
  api_key: '',
  model: '',
  models: '',
  timeout: 60,
})

const isNew = computed(() => !providers.value.some((p) => p.provider_id === form.value.provider_id))

async function load() {
  loading.value = true
  const res = await window.api.get('/api/ai/providers')
  if (res.ok) {
    const data = res.data as { providers?: Provider[]; active_provider?: string; templates?: Template[] }
    providers.value = data.providers || []
    templates.value = data.templates || []
    activeId.value = data.active_provider || ''
    error.value = ''
  } else {
    error.value = res.error || `HTTP ${res.status}`
  }
  loading.value = false

  const health = await window.api.health()
  version.value = health?.version || '—'
  port.value = health?.port || 0
  pid.value = health?.pid || 0
}

function applyTemplate(templateId: string) {
  const found = templates.value.find((t) => t.provider_id === templateId)
  if (!found) return
  form.value = {
    provider_id: found.provider_id,
    name: found.name,
    base_url: found.base_url,
    api_key: '',
    model: found.default_model,
    models: found.models,
    timeout: found.timeout || 60,
  }
  editing.value = true
}

function onTemplateChange(event: Event) {
  applyTemplate((event.target as HTMLSelectElement).value)
}

function openDataDir() {
  void window.api.openDataDir()
}

function startCreate() {
  editing.value = true
  form.value = {
    provider_id: '', name: '', base_url: '', api_key: '',
    model: '', models: '', timeout: 60,
  }
}

function startEdit(provider: Provider) {
  editing.value = true
  form.value = {
    provider_id: provider.provider_id,
    name: provider.name,
    base_url: provider.base_url,
    api_key: provider.api_key,
    model: provider.model,
    models: provider.models,
    timeout: provider.timeout,
  }
}

async function save() {
  if (!form.value.provider_id.trim()) {
    error.value = 'provider_id 不能为空'
    return
  }
  busy.value = true
  const res = await window.api.post('/api/ai/providers', {
    ...form.value,
    provider_id: form.value.provider_id.trim(),
    timeout: Number(form.value.timeout) || 60,
  })
  busy.value = false
  if (res.ok) {
    notice.value = `已保存：${form.value.provider_id}`
    editing.value = false
    await load()
  } else {
    error.value = res.error || '保存失败'
  }
}

async function activate(provider: Provider) {
  const res = await window.api.post(`/api/ai/providers/${encodeURIComponent(provider.provider_id)}/activate`)
  if (res.ok) {
    notice.value = `已切换默认：${provider.provider_id}`
    await load()
  } else {
    error.value = res.error || '切换失败'
  }
}

async function test(provider: Provider) {
  busy.value = true
  const res = await window.api.post(`/api/ai/providers/${encodeURIComponent(provider.provider_id)}/test`)
  busy.value = false
  if (res.ok) {
    const data = res.data as { ok?: boolean; message?: string; detail?: string }
    notice.value = data.message || (data.ok ? '连接正常' : '连接失败')
  } else {
    error.value = res.error || '测试失败'
  }
}

async function remove(provider: Provider) {
  const ok = await window.api.confirm(
    `删除 AI 提供商「${provider.name || provider.provider_id}」？`,
    '删除后需要重新填写地址与密钥。',
  )
  if (!ok) return
  busy.value = true
  const res = await window.api.del(`/api/ai/providers/${encodeURIComponent(provider.provider_id)}`)
  busy.value = false
  if (res.ok) {
    notice.value = `已删除：${provider.provider_id}`
    await load()
  } else {
    error.value = res.error || '删除失败'
  }
}

onMounted(load)
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <h1>设置</h1>
        <p>AI 提供商与运行信息</p>
      </div>
      <AppButton :disabled="loading" @click="load">刷新</AppButton>
    </header>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="notice" class="notice">{{ notice }}</p>

    <Panel title="AI 提供商" hint="密钥仅保存在本机 ai_models.json">
      <div class="toolbar">
        <select class="field" @change="onTemplateChange">
          <option value="">从模板新建…</option>
          <option v-for="t in templates" :key="t.provider_id" :value="t.provider_id">
            {{ t.name }}
          </option>
        </select>
        <AppButton @click="startCreate">自定义新建</AppButton>
      </div>

      <ul v-if="providers.length" class="list">
        <li v-for="provider in providers" :key="provider.provider_id">
          <span class="main">
            <b>{{ provider.name || provider.provider_id }}</b>
            <span v-if="provider.active" class="badge">默认</span>
            <span class="sub">{{ provider.provider_id }} · {{ provider.model || '未指定模型' }}</span>
          </span>
          <span class="url">{{ provider.base_url }}</span>
          <span class="key" :class="{ ok: provider.has_key }">
            {{ provider.has_key ? '密钥已配置' : '未配置密钥' }}
          </span>
          <span class="actions">
            <AppButton size="sm" variant="ghost" :disabled="busy || provider.active" @click="activate(provider)">
              设为默认
            </AppButton>
            <AppButton size="sm" variant="ghost" :disabled="busy" @click="test(provider)">测试</AppButton>
            <AppButton size="sm" variant="ghost" @click="startEdit(provider)">编辑</AppButton>
            <AppButton size="sm" variant="ghost" :disabled="busy" @click="remove(provider)">删除</AppButton>
          </span>
        </li>
      </ul>
      <p v-else-if="!loading" class="empty">还没有配置 AI 提供商。可用上方的模板快速创建。</p>

      <div v-if="editing" class="form">
        <div class="row">
          <label>ID</label>
          <input v-model="form.provider_id" class="field" placeholder="如 openai / ollama" :disabled="!isNew" />
          <label>名称</label>
          <input v-model="form.name" class="field" placeholder="显示名" />
        </div>
        <div class="row">
          <label>地址</label>
          <input v-model="form.base_url" class="field grow" placeholder="https://api.example.com/v1" />
        </div>
        <div class="row">
          <label>密钥</label>
          <input v-model="form.api_key" class="field grow" placeholder="留空或保持掩码值则沿用已存密钥" />
        </div>
        <div class="row">
          <label>模型</label>
          <input v-model="form.model" class="field" placeholder="默认模型" />
          <label>超时</label>
          <input v-model="form.timeout" class="field short" type="number" min="5" />
        </div>
        <div class="row end">
          <AppButton variant="primary" :disabled="busy" @click="save">保存</AppButton>
          <AppButton variant="ghost" @click="editing = false">取消</AppButton>
        </div>
      </div>
    </Panel>

    <Panel title="运行信息">
      <template #actions>
        <AppButton size="sm" variant="ghost" @click="openDataDir">打开数据目录</AppButton>
      </template>
      <dl class="info">
        <dt>应用版本</dt><dd>{{ version }}</dd>
        <dt>sidecar 端口</dt><dd>{{ port || '—' }}</dd>
        <dt>sidecar PID</dt><dd>{{ pid || '—' }}</dd>
        <dt>接口鉴权</dt><dd>每次启动随机 token，仅本机回环</dd>
        <dt>数据位置</dt><dd>%APPDATA%\FileNest\filenest.db</dd>
      </dl>
    </Panel>
  </div>
</template>

<style scoped>
.page { display: flex; flex-direction: column; gap: var(--space-4); max-width: 1000px; }
.page-head { display: flex; align-items: flex-end; justify-content: space-between; }
h1 { margin: 0; font-size: 20px; }
.page-head p { margin: 2px 0 0; color: var(--dim); font-size: 12px; }

.toolbar { display: flex; gap: var(--space-2); margin-bottom: var(--space-3); }
.field {
  height: 32px;
  padding: 0 10px;
  color: var(--text);
  background: var(--bg);
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  font-family: inherit;
  font-size: 13px;
  outline: none;
}
.field:focus { border-color: var(--primary); }
.field:disabled { color: var(--dim); }
.grow { flex: 1; min-width: 220px; }
.short { width: 90px; }

.list { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
.list li {
  display: grid;
  grid-template-columns: minmax(200px, 1.2fr) minmax(160px, 1fr) 96px auto;
  align-items: center;
  gap: var(--space-3);
  padding: 8px;
  border-radius: var(--radius-sm);
}
.list li:hover { background: #202537; }
.main { display: flex; align-items: center; gap: var(--space-2); min-width: 0; }
.main b { font-size: 13px; font-weight: 600; }
.sub { color: var(--dim); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.badge {
  padding: 1px 6px;
  color: var(--ok);
  font-size: 11px;
  border: 1px solid rgba(16, 185, 129, .5);
  border-radius: 999px;
}
.url { color: var(--muted); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.key { color: var(--warn); font-size: 12px; }
.key.ok { color: var(--ok); }
.actions { display: flex; justify-content: flex-end; gap: var(--space-1); }

.form { margin-top: var(--space-4); padding-top: var(--space-4); border-top: 1px solid var(--line); display: grid; gap: var(--space-2); }
.row { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; }
.row label { color: var(--dim); font-size: 12px; width: 44px; }
.row.end { justify-content: flex-end; }

.info { display: grid; grid-template-columns: 120px 1fr; gap: 6px var(--space-3); margin: 0; font-size: 13px; }
.info dt { color: var(--dim); }
.info dd { margin: 0; color: var(--muted); }

.error { margin: 0; padding: 10px 12px; color: #fecaca; background: #3f1d1d; border-radius: var(--radius-sm); }
.notice { margin: 0; padding: 10px 12px; color: #bbf7d0; background: #14321f; border-radius: var(--radius-sm); }
.empty { margin: 0; color: var(--dim); font-size: 13px; }
</style>
