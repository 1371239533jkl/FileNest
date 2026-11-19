import fs from 'node:fs/promises'

const TEXT_EXT = new Set([
  '.txt', '.md', '.log', '.json', '.csv', '.py', '.js', '.ts', '.vue', '.yml',
  '.yaml', '.ini', '.cfg', '.toml', '.sql', '.html', '.css', '.sh',
])

export interface TextHead {
  ok: boolean
  data?: string
  error?: string
}

/** 只读文本文件头部，供预览面板使用；拦截超大文件与非文本扩展名 */
export async function readTextHead(path: string, limit = 8192): Promise<TextHead> {
  if (typeof path !== 'string' || !path || path.length > 4096 || path.includes('\0')) {
    return { ok: false, error: '路径非法' }
  }
  const ext = (path.toLowerCase().match(/\.[^.\\/]+$/) || [''])[0]
  if (!TEXT_EXT.has(ext)) {
    return { ok: false, error: '该类型不支持文本预览' }
  }
  try {
    const stat = await fs.stat(path)
    if (!stat.isFile()) return { ok: false, error: '不是文件' }
    if (stat.size > 8 << 20) return { ok: false, error: '文件过大' }
    const handle = await fs.open(path, 'r')
    try {
      const buffer = Buffer.alloc(Math.min(limit, stat.size || limit))
      const { bytesRead } = await handle.read(buffer, 0, buffer.length, 0)
      return { ok: true, data: buffer.subarray(0, bytesRead).toString('utf8') }
    } finally {
      await handle.close()
    }
  } catch (err) {
    return { ok: false, error: (err as Error).message }
  }
}
