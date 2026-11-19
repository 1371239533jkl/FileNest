import { getSidecarInfo, getToken } from './sidecar'

// 渲染层只能访问白名单路径，避免 preload 变成任意请求通道
const ALLOWED = [
  /^\/api\/dashboard$/,
  /^\/api\/tasks(\/\d+)?$/,
  /^\/api\/files(\?|$)/,
  /^\/api\/tags\/full(\?|$)/,
]

export interface ApiResult {
  ok: boolean
  status: number
  data?: unknown
  error?: string
}

/** 缩略图：返回 data URI，避免渲染层直连网络 */
export async function apiThumb(path: string, size = 256): Promise<ApiResult> {
  const { status, port } = getSidecarInfo()
  if (status !== 'ok') return { ok: false, status: 503, error: 'sidecar not ready' }
  try {
    const url = `http://127.0.0.1:${port}/api/thumb?size=${size}&path=${encodeURIComponent(path)}`
    const res = await fetch(url, {
      headers: { 'x-api-key': getToken() },
      signal: AbortSignal.timeout(15000),
    })
    if (!res.ok) return { ok: false, status: res.status, error: await res.text() }
    const buffer = Buffer.from(await res.arrayBuffer())
    return { ok: true, status: res.status, data: `data:image/jpeg;base64,${buffer.toString('base64')}` }
  } catch (err) {
    return { ok: false, status: 0, error: (err as Error).message }
  }
}

export async function apiGet(path: string): Promise<ApiResult> {
  if (!ALLOWED.some((re) => re.test(path))) {
    return { ok: false, status: 403, error: `path not allowed: ${path}` }
  }
  const { status, port } = getSidecarInfo()
  if (status !== 'ok') {
    return { ok: false, status: 503, error: 'sidecar not ready' }
  }
  try {
    const res = await fetch(`http://127.0.0.1:${port}${path}`, {
      headers: { 'x-api-key': getToken() },
      signal: AbortSignal.timeout(15000),
    })
    if (!res.ok) {
      return { ok: false, status: res.status, error: await res.text() }
    }
    return { ok: true, status: res.status, data: await res.json() }
  } catch (err) {
    return { ok: false, status: 0, error: (err as Error).message }
  }
}
