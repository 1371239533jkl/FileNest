import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'

// html:false —— 不解析原始 HTML；linkify:false —— 不自动造链接，避免协议注入面
const md = new MarkdownIt({ html: false, linkify: false, breaks: true })

const ALLOWED_TAGS = [
  'p', 'br', 'strong', 'em', 'del', 'code', 'pre', 'blockquote',
  'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'a', 'hr',
  'table', 'thead', 'tbody', 'tr', 'th', 'td',
]

/** 渲染 AI 回复的 Markdown，渲染结果统一净化后再交给 v-html */
export function renderMarkdown(source: string): string {
  const html = md.render(source || '')
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS,
    ALLOWED_ATTR: ['href', 'title', 'class'],
    ALLOWED_URI_REGEXP: /^(?:https?|mailto):/i,
  })
}
