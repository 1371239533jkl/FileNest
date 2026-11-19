<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppButton from '../components/AppButton.vue'
import Panel from '../components/Panel.vue'
import { formatCount } from '../lib/format'

interface Tag {
  tag_name: string
  file_count: number
  aliases: string[]
}

const tags = ref<Tag[]>([])
const keyword = ref('')
const newTag = ref('')
const editing = ref<string | null>(null)
const editValue = ref('')
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')

const filtered = computed(() => {
  const word = keyword.value.trim().toLowerCase()
  if (!word) return tags.value
  return tags.value.filter((t) => t.tag_name.toLowerCase().includes(word))
})

async function load() {
  loading.value = true
  const res = await window.api.get('/api/tags/full')
  if (res.ok) {
    tags.value = (res.data as { tags?: Tag[] }).tags || []
    error.value = ''
  } else {
    error.value = res.error || `HTTP ${res.status}`
  }
  loading.value = false
}

async function createTag() {
  const name = newTag.value.trim()
  if (!name) return
  busy.value = true
  const res = await window.api.post('/api/tags', { tag: name })
  busy.value = false
  if (res.ok) {
    newTag.value = ''
    notice.value = `已添加：${name}`
    await load()
  } else {
    error.value = res.error || '添加失败'
  }
}

function startRename(tag: Tag) {
  editing.value = tag.tag_name
  editValue.value = tag.tag_name
  notice.value = ''
}

async function commitRename() {
  const oldName = editing.value
  const next = editValue.value.trim()
  if (!oldName) return
  if (!next || next === oldName) {
    editing.value = null
    return
  }
  busy.value = true
  const query = `?old_name=${encodeURIComponent(oldName)}&new_name=${encodeURIComponent(next)}`
  const res = await window.api.post(`/api/tags/rename${query}`)
  busy.value = false
  editing.value = null
  if (res.ok) {
    notice.value = `已重命名：${oldName} → ${next}`
    await load()
  } else {
    error.value = res.error || '重命名失败'
  }
}

async function removeTag(tag: Tag) {
  const ok = await window.api.confirm(
    `删除标签「${tag.tag_name}」？`,
    tag.file_count
      ? `该标签关联 ${tag.file_count} 个文件，删除后仅移除标签本身，不会删除文件。`
      : '该标签还没有关联文件。',
  )
  if (!ok) return
  busy.value = true
  const res = await window.api.del(`/api/tags/${encodeURIComponent(tag.tag_name)}`)
  busy.value = false
  if (res.ok) {
    notice.value = `已删除：${tag.tag_name}`
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
        <h1>标签</h1>
        <p>{{ formatCount(tags.length) }} 个标签，用于跨目录归类</p>
      </div>
      <AppButton :disabled="loading" @click="load">刷新</AppButton>
    </header>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="notice" class="notice">{{ notice }}</p>

    <Panel title="全部标签">
      <div class="form">
        <input
          v-model="newTag"
          class="field grow-field"
          placeholder="新标签名，回车添加"
          @keyup.enter="createTag"
        />
        <AppButton variant="primary" :disabled="busy || !newTag.trim()" @click="createTag">
          添加
        </AppButton>
        <input v-model="keyword" class="field" placeholder="筛选" />
      </div>

      <ul v-if="filtered.length" class="list">
        <li v-for="tag in filtered" :key="tag.tag_name">
          <span class="name">
            <template v-if="editing === tag.tag_name">
              <input
                v-model="editValue"
                class="field inline"
                autofocus
                @keyup.enter="commitRename"
                @keyup.esc="editing = null"
              />
              <AppButton size="sm" variant="primary" :disabled="busy" @click="commitRename">
                保存
              </AppButton>
              <AppButton size="sm" variant="ghost" @click="editing = null">取消</AppButton>
            </template>
            <template v-else>
              <span class="tag">{{ tag.tag_name }}</span>
              <span v-if="tag.aliases?.length" class="alias">
                别名：{{ tag.aliases.join('、') }}
              </span>
            </template>
          </span>

          <span class="count">{{ tag.file_count }} 个文件</span>

          <span class="actions">
            <AppButton
              v-if="editing !== tag.tag_name"
              size="sm"
              variant="ghost"
              :disabled="busy"
              @click="startRename(tag)"
            >重命名</AppButton>
            <AppButton
              v-if="editing !== tag.tag_name"
              size="sm"
              variant="ghost"
              :disabled="busy"
              @click="removeTag(tag)"
            >删除</AppButton>
          </span>
        </li>
      </ul>
      <p v-else-if="!loading" class="empty">
        {{ keyword ? '没有匹配的标签' : '还没有标签。先在上方输入名称添加一个。' }}
      </p>
    </Panel>
  </div>
</template>

<style scoped>
.page { display: flex; flex-direction: column; gap: var(--space-4); max-width: 960px; }
.page-head { display: flex; align-items: flex-end; justify-content: space-between; }
h1 { margin: 0; font-size: 20px; }
.page-head p { margin: 2px 0 0; color: var(--dim); font-size: 12px; }

.form { display: flex; align-items: center; gap: var(--space-2); margin-bottom: var(--space-3); }
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
.grow-field { flex: 1; min-width: 180px; }
.inline { width: 180px; height: 28px; }

.list { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
.list li {
  display: grid;
  grid-template-columns: 1fr 96px 168px;
  align-items: center;
  gap: var(--space-3);
  padding: 7px 8px;
  border-radius: var(--radius-sm);
}
.list li:hover { background: #202537; }
.name { display: flex; align-items: center; gap: var(--space-2); min-width: 0; }
.tag { font-size: 13px; }
.alias { color: var(--dim); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.count { color: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; }
.actions { display: flex; justify-content: flex-end; gap: var(--space-1); }

.error { margin: 0; padding: 10px 12px; color: #fecaca; background: #3f1d1d; border-radius: var(--radius-sm); }
.notice { margin: 0; padding: 10px 12px; color: #bbf7d0; background: #14321f; border-radius: var(--radius-sm); }
.empty { margin: 0; color: var(--dim); font-size: 13px; }
</style>
