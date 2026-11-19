import { spawn, ChildProcess } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import net from 'node:net'
import path from 'node:path'
import { app } from 'electron'

export interface SidecarInfo {
  status: 'starting' | 'ok' | 'failed'
  port: number
  version?: string
  pid?: number
  error?: string
}

const DEV_ROOT = path.resolve(app.getAppPath(), '..')
const PACKAGED_DIR = path.join(process.resourcesPath, 'sidecar')
const PACKAGED = app.isPackaged

// 每次启动重新生成；sidecar 以 SFM_API_KEY 读取，所有 /api 请求需带 x-api-key
const TOKEN = randomBytes(32).toString('hex')

const CWD = PACKAGED ? PACKAGED_DIR : DEV_ROOT
const EXE = PACKAGED
  ? path.join(PACKAGED_DIR, 'filenest-service.exe')
  : (process.env.FILENEST_PYTHON || path.join(DEV_ROOT, '.venv', 'Scripts', 'python.exe'))
const ARGS = PACKAGED ? [] : ['server.py']

let child: ChildProcess | null = null
let info: SidecarInfo = { status: 'starting', port: 0 }

function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const srv = net.createServer()
    srv.once('error', reject)
    srv.listen(0, '127.0.0.1', () => {
      const port = (srv.address() as net.AddressInfo).port
      srv.close(() => resolve(port))
    })
  })
}

export function getSidecarInfo(): SidecarInfo {
  return info
}

export async function startSidecar(timeoutMs = 20000): Promise<SidecarInfo> {
  const port = await freePort()
  info = { status: 'starting', port }

  child = spawn(EXE, ARGS, {
    cwd: CWD,
    env: {
      ...process.env,
      SFM_HOST: '127.0.0.1',
      SFM_PORT: String(port),
      SFM_API_KEY: TOKEN,
      // 冻结后 __file__ 在 resources 下，数据库必须落到用户数据目录
      SFM_DB: path.join(app.getPath('userData'), 'filenest.db'),
      PYTHONUNBUFFERED: '1',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  })

  child.on('error', (err) => {
    info = { ...info, status: 'failed', error: `spawn failed: ${err.message}` }
  })
  child.stdout?.on('data', (d) => process.stdout.write(`[sidecar] ${d}`))
  child.stderr?.on('data', (d) => process.stderr.write(`[sidecar] ${d}`))
  child.on('exit', (code) => {
    if (info.status === 'ok') {
      info = { ...info, status: 'failed', error: `sidecar exited (${code})` }
    }
  })

  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      return (info = { status: 'failed', port, error: `sidecar exited (${child.exitCode})` })
    }
    try {
      const res = await fetch(`http://127.0.0.1:${port}/health`)
      if (res.ok) {
        const body = (await res.json()) as { version?: string; pid?: number }
        return (info = { status: 'ok', port, version: body.version, pid: body.pid })
      }
    } catch {
      // 未就绪，继续等
    }
    await new Promise((r) => setTimeout(r, 150))
  }
  return (info = { status: 'failed', port, error: 'sidecar health timeout' })
}

export async function stopSidecar(): Promise<void> {
  if (!child || child.killed) return
  const pid = child.pid
  const port = info.port
  child = null

  // 先请服务端自行退出；失败再强杀，两条路都能保证不留孤儿
  try {
    await fetch(`http://127.0.0.1:${port}/api/shutdown`, {
      method: 'POST',
      headers: { 'x-api-key': TOKEN },
      signal: AbortSignal.timeout(1000),
    })
    await new Promise((r) => setTimeout(r, 400))
  } catch {
    // 已经退出或拒绝连接，走下面的强杀
  }

  if (process.platform === 'win32' && pid) {
    spawn('taskkill', ['/pid', String(pid), '/T', '/F'], { windowsHide: true })
  } else if (pid) {
    try {
      process.kill(-pid, 'SIGTERM')
    } catch {
      // 进程已不存在
    }
  }
}
