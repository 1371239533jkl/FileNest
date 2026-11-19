import { app, BrowserWindow, ipcMain } from 'electron'
import path from 'node:path'
import { getSidecarInfo, startSidecar, stopSidecar } from './sidecar'

const SMOKE = process.argv.includes('--smoke')
let win: BrowserWindow | null = null

function createWindow(): BrowserWindow {
  const w = new BrowserWindow({
    width: 1100,
    height: 720,
    show: false,
    backgroundColor: '#0f0f1a',
    webPreferences: {
      preload: path.join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })
  w.once('ready-to-show', () => w.show())
  w.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
  w.webContents.on('will-navigate', (e) => e.preventDefault())
  void w.loadFile(path.join(__dirname, '../renderer/index.html'))
  return w
}

if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (win) {
      win.show()
      win.focus()
    }
  })

  app.whenReady().then(async () => {
    const sidecar = await startSidecar()
    console.log(`[main] sidecar ${JSON.stringify(sidecar)}`)

    ipcMain.handle('app:health', () => getSidecarInfo())

    win = createWindow()

    if (SMOKE) {
      win.webContents.once('did-finish-load', () => {
        console.log('[smoke] renderer loaded')
        console.log(`[smoke] ${sidecar.status === 'ok' ? 'PASS' : 'FAIL'}`)
        process.exitCode = sidecar.status === 'ok' ? 0 : 1
        app.quit() // 走 before-quit 收掉 sidecar，避免孤儿进程
      })
    }
  })

  app.on('window-all-closed', () => app.quit())

  // 退出前先让 sidecar 优雅收尾（异步），完成后再真正退出
  let quitting = false
  app.on('before-quit', (event) => {
    if (quitting) return
    quitting = true
    event.preventDefault()
    void stopSidecar().finally(() => app.quit())
  })
}
