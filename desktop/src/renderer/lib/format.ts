export function formatBytes(bytes?: number | null): string {
  const value = Number(bytes) || 0
  if (value < 1024) return `${value} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let size = value / 1024
  let i = 0
  while (size >= 1024 && i < units.length - 1) {
    size /= 1024
    i++
  }
  return `${size.toFixed(size >= 100 ? 0 : 1)} ${units[i]}`
}

export function formatCount(value?: number | null): string {
  const n = Number(value) || 0
  return n >= 10000 ? `${(n / 10000).toFixed(1)} 万` : String(n)
}

export function formatTime(value?: string | null): string {
  if (!value) return ''
  return String(value).replace('T', ' ').slice(0, 16)
}

export const TYPE_NAMES: Record<string, string> = {
  image: '图片',
  document: '文档',
  code: '代码',
  video: '视频',
  audio: '音频',
  archive: '压缩包',
  executable: '可执行',
  font: '字体',
  other: '其他',
}

export function typeName(type?: string | null): string {
  return (type && TYPE_NAMES[type]) || String(type || '其他')
}

const OP_NAMES: Record<string, string> = {
  rename: '重命名',
  move: '移动',
  delete: '删除',
  dedup: '去重',
  classify: '分类',
  restore: '恢复',
  purge: '永久删除',
}

export function opName(type?: string | null): string {
  return (type && OP_NAMES[type]) || String(type || '操作')
}
