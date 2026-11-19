<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import AppButton from '../components/AppButton.vue'
import { renderMarkdown } from '../lib/markdown'

interface Message {
  role: 'user' | 'assistant'
  content: string
  matches?: number
  error?: string
}

const SUGGESTIONS = [
  '帮我找最近修改的文档',
  '有哪些重复文件值得清理',
  '按类型统计一下我的文件',
]

const messages = ref<Message[]>([])
const input = ref('')
const streaming = ref(false)
const scroller = ref<HTMLElement | null>(null)
let unsubscribe: (() => void) | null = null

function scrollToBottom() {
  void nextTick(() => {
    if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight
  })
}

function lastAssistant(): Message | undefined {
  const last = messages.value[messages.value.length - 1]
  return last && last.role === 'assistant' ? last : undefined
}

async function send() {
  const text = input.value.trim()
  if (!text || streaming.value) return

  messages.value.push({ role: 'user', content: text })
  messages.value.push({ role: 'assistant', content: '' })
  input.value = ''
  streaming.value = true
  scrollToBottom()

  const res = await window.api.chatStream(text)
  const target = lastAssistant()
  if (!res.ok && target) {
    target.error = res.error || '请求失败'
  }
  streaming.value = false
  scrollToBottom()
}

function useSuggestion(text: string) {
  input.value = text
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    void send()
  }
}

function onContentClick(event: MouseEvent) {
  const anchor = (event.target as HTMLElement).closest('a')
  if (!anchor) return
  event.preventDefault()
  void window.api.openExternal(anchor.getAttribute('href') || '')
}

onMounted(() => {
  unsubscribe = window.api.onChatEvent((payload: any) => {
    const target = lastAssistant()
    if (!target) return
    if (payload.type === 'meta') {
      target.matches = payload.matches
    } else if (payload.type === 'delta') {
      target.content += payload.text
    } else if (payload.type === 'error') {
      target.error = payload.message
    } else if (payload.type === 'done') {
      streaming.value = false
    }
    scrollToBottom()
  })
})

onBeforeUnmount(() => {
  unsubscribe?.()
})
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <h1>AI 对话</h1>
        <p>基于本地索引回答，不联网检索你的文件</p>
      </div>
    </header>

    <div ref="scroller" class="thread">
      <div v-if="!messages.length" class="empty">
        <p class="empty-title">问点什么</p>
        <div class="chips">
          <button
            v-for="item in SUGGESTIONS"
            :key="item"
            data-suggest
            @click="useSuggestion(item)"
          >{{ item }}</button>
        </div>
      </div>

      <div v-for="(message, index) in messages" :key="index" class="msg" :class="message.role">
        <div class="bubble">
          <template v-if="message.role === 'assistant'">
            <p v-if="message.error" class="err">{{ message.error }}</p>
            <div
              v-else
              class="md"
              @click="onContentClick"
              v-html="renderMarkdown(message.content)"
            />
            <p v-if="message.matches !== undefined" class="meta">
              匹配 {{ message.matches }} 个文件
            </p>
          </template>
          <p v-else class="plain">{{ message.content }}</p>
        </div>
      </div>
    </div>

    <div class="composer">
      <textarea
        v-model="input"
        class="box"
        rows="2"
        placeholder="输入问题，Enter 发送，Shift+Enter 换行"
        :disabled="streaming"
        @keydown="onKeydown"
      />
      <AppButton data-send variant="primary" :disabled="streaming || !input.trim()" @click="send">
        {{ streaming ? '回答中…' : '发送' }}
      </AppButton>
    </div>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  height: calc(100vh - 52px - var(--space-5) * 2);
  max-width: 900px;
}
.page-head h1 { margin: 0; font-size: 20px; }
.page-head p { margin: 2px 0 0; color: var(--dim); font-size: 12px; }

.thread {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding-right: var(--space-2);
}

.empty { margin: auto; text-align: center; color: var(--dim); }
.empty-title { margin: 0 0 var(--space-3); font-size: 13px; }
.chips { display: flex; gap: var(--space-2); flex-wrap: wrap; justify-content: center; }
.chips button {
  padding: 6px 12px;
  color: var(--muted);
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 999px;
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
}
.chips button:hover { color: var(--text); border-color: var(--primary); }

.msg { display: flex; }
.msg.user { justify-content: flex-end; }
.bubble {
  max-width: 82%;
  padding: 10px 14px;
  border-radius: var(--radius);
  border: 1px solid var(--line);
  background: var(--card);
}
.msg.user .bubble {
  background: #23304d;
  border-color: #31415f;
}
.plain { margin: 0; font-size: 14px; white-space: pre-wrap; }
.meta { margin: 6px 0 0; color: var(--dim); font-size: 11px; }
.err { margin: 0; color: #fca5a5; font-size: 13px; }

.composer { display: flex; gap: var(--space-2); align-items: flex-end; }
.box {
  flex: 1;
  padding: 8px 12px;
  color: var(--text);
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  font-family: inherit;
  font-size: 14px;
  line-height: 1.6;
  resize: none;
  outline: none;
}
.box:focus { border-color: var(--primary); }

/* Markdown 样式见 styles/markdown.css（与组件总览共用） */
</style>
