import { spawn, ChildProcess } from 'node:child_process'
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

export function stopSidecar(): void {
  if (!child || child.killed) return
  const pid = child.pid
  child = null
  if (process.platform === 'win32' && pid) {
    // Windows 上没有进程组信号，用 taskkill 连子进程一起收掉，避免孤儿
    spawn('taskkill', ['/pid', String(pid), '/T', '/F'], { windowsHide: true })
  } else {
    process.kill(-pid!, 'SIGTERM')
  }
}
