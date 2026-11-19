import { getSidecarInfo, getToken } from './sidecar'

// 渲染层只能访问白名单路径，避免 preload 变成任意请求通道
const GET_ALLOWED = [
  /^\/api\/dashboard$/,
  /^\/api\/tasks(\/\d+)?$/,
  /^\/api\/files(\?|$)/,
  /^\/api\/duplicates(\?|$)/,
  /^\/api\/duplicates\/\d+$/,
  /^\/api\/tags\/full(\?|$)/,
]
const POST_ALLOWED = [
  /^\/api\/scan\/start$/,
  /^\/api\/scan\/cancel(\?|$)/,
  /^\/api\/duplicates\/clean$/,
  /^\/api\/duplicates\/\d+\/suggest(\?|$)/,
  /^\/api\/dedup\/start(\?|$)/,
]

export interface ApiResult {
  ok: boolean
  status: number
  data?: unknown
  error?: string
}

async function request(
  method: 'GET' | 'POST',
  path: string,
  body?: unknown,
): Promise<ApiResult> {
  const allowlist = method === 'GET' ? GET_ALLOWED : POST_ALLOWED
  if (!allowlist.some((re) => re.test(path))) {
    return { ok: false, status: 403, error: `path not allowed: ${method} ${path}` }
  }
  const { status, port } = getSidecarInfo()
  if (status !== 'ok') {
    return { ok: false, status: 503, error: 'sidecar not ready' }
  }
  try {
    const res = await fetch(`http://127.0.0.1:${port}${path}`, {
      method,
      headers: {
        'x-api-key': getToken(),
        ...(body ? { 'Content-Type': 'application/json' } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(30000),
    })
    if (!res.ok) {
      return { ok: false, status: res.status, error: await res.text() }
    }
    return { ok: true, status: res.status, data: await res.json() }
  } catch (err) {
    return { ok: false, status: 0, error: (err as Error).message }
  }
}

export function apiGet(path: string): Promise<ApiResult> {
  return request('GET', path)
}

export function apiPost(path: string, body?: unknown): Promise<ApiResult> {
  return request('POST', path, body)
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
