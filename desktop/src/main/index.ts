import { app, BrowserWindow, clipboard, dialog, ipcMain, shell } from 'electron'
import fs from 'node:fs'
import path from 'node:path'
import { apiGet, apiPost, apiThumb } from './api'
import { readTextHead } from './files'
import { getSidecarInfo, startSidecar, stopSidecar } from './sidecar'

const SHOT = process.argv.find((arg) => arg.startsWith('--shot='))?.split('=')[1]

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
    ipcMain.handle('api:get', (_event, requestPath: string) => apiGet(requestPath))
    ipcMain.handle('shell:open', (_event, target: string) => shell.openPath(target))
    ipcMain.handle('shell:reveal', (_event, target: string) => shell.showItemInFolder(target))
    ipcMain.handle('clipboard:write', (_event, text: string) => clipboard.writeText(String(text)))
    ipcMain.handle('api:thumb', (_event, target: string, size?: number) => apiThumb(target, size))
    ipcMain.handle('api:post', (_event, target: string, body?: unknown) => apiPost(target, body))
    ipcMain.handle('file:readText', (_event, target: string) => readTextHead(target))
    ipcMain.handle('dialog:confirm', async (_event, title: string, message: string) => {
      const { response } = await dialog.showMessageBox({
        type: 'warning',
        buttons: ['取消', '确认'],
        defaultId: 0,
        cancelId: 0,
        title: String(title).slice(0, 80),
        message: String(title).slice(0, 200),
        detail: String(message).slice(0, 1000),
      })
      return response === 1
    })
    ipcMain.handle('dialog:pickDirectory', async () => {
      const result = await dialog.showOpenDialog({
        properties: ['openDirectory'],
        title: '选择要扫描的目录',
      })
      return result.canceled ? '' : result.filePaths[0]
    })

    win = createWindow()

    if (SMOKE) {
      win.webContents.once('did-finish-load', () => {
        console.log('[smoke] renderer loaded')
        console.log(`[smoke] ${sidecar.status === 'ok' ? 'PASS' : 'FAIL'}`)
        process.exitCode = sidecar.status === 'ok' ? 0 : 1
        app.quit() // 走 before-quit 收掉 sidecar，避免孤儿进程
      })
    }

    if (SHOT) {
      win.webContents.once('did-finish-load', async () => {
        win?.show()
        await new Promise((r) => setTimeout(r, 1500))
        const tabArg = process.argv
          .find((arg) => arg.startsWith('--shot-tab='))
          ?.split('=')[1]
        if (tabArg && /^[a-z-]+$/.test(tabArg)) {
          await win!.webContents.executeJavaScript(
            `document.querySelector('[data-tab="${tabArg}"]')?.click()`,
          )
          await new Promise((r) => setTimeout(r, 1500))
          const rowArg = process.argv
            .find((arg) => arg.startsWith('--shot-row='))
            ?.split('=')[1]
          if (rowArg !== undefined) {
            const needle = JSON.stringify(rowArg)
            await win!.webContents.executeJavaScript(
              `([...document.querySelectorAll('.item')]
                 .find((el) => el.textContent.includes(${needle}))
                 || document.querySelector('.item'))?.click()`,
            )
            await new Promise((r) => setTimeout(r, 900))
          }
          const scanArg = process.argv
            .find((arg) => arg.startsWith('--shot-scan='))
            ?.split('=')[1]
          if (scanArg) {
            await win!.webContents.executeJavaScript(`
              (() => {
                const input = document.querySelector('input.dir')
                const setter = Object.getOwnPropertyDescriptor(
                  HTMLInputElement.prototype, 'value').set
                setter.call(input, ${JSON.stringify(scanArg)})
                input.dispatchEvent(new Event('input', { bubbles: true }))
                document.querySelector('.form .btn.primary')?.click()
              })()
            `)
            await new Promise((r) => setTimeout(r, 2500))
          }

          // 打开第一个重复组（选择器含空格，用固定标志避免命令行拆分）
          if (process.argv.includes('--shot-group')) {
            await win!.webContents.executeJavaScript(
              `document.querySelector('.groups li')?.click()`,
            )
            await new Promise((r) => setTimeout(r, 1200))
          }

          if (process.argv.includes('--shot-perf')) {
            const perf = await win!.webContents.executeJavaScript(
              `window.__scrollPerf ? window.__scrollPerf() : null`,
            )
            if (perf) console.log(`[perf] ${JSON.stringify(perf)}`)
          }
        }
        const image = await win!.webContents.capturePage()
        fs.writeFileSync(SHOT, image.toPNG())
        console.log(`[shot] saved ${SHOT}`)
        app.quit()
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
