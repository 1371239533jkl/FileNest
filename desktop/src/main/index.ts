import { app, BrowserWindow, clipboard, dialog, ipcMain, shell } from 'electron'
import fs from 'node:fs'
import path from 'node:path'
import { apiDelete, apiGet, apiPost, apiThumb } from './api'
import { readTextHead } from './files'
import { getSidecarInfo, getToken, startSidecar, stopSidecar } from './sidecar'

// 只按第一个 '=' 切分：参数值里可能再含 '='（如 CSS 选择器 [data-seg=ops]）
function argValue(prefix: string): string | undefined {
  const hit = process.argv.find((arg) => arg.startsWith(prefix))
  return hit === undefined ? undefined : hit.slice(prefix.length)
}

const SHOT = argValue('--shot=')

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
    ipcMain.handle('shell:openExternal', (_event, url: string) => {
      if (!/^https?:\/\//i.test(url)) return false
      void shell.openExternal(url)
      return true
    })
    ipcMain.handle('shell:reveal', (_event, target: string) => shell.showItemInFolder(target))
    ipcMain.handle('clipboard:write', (_event, text: string) => clipboard.writeText(String(text)))
    ipcMain.handle('api:thumb', (_event, target: string, size?: number) => apiThumb(target, size))
    ipcMain.handle('api:post', (_event, target: string, body?: unknown) => apiPost(target, body))
    ipcMain.handle('api:delete', (_event, target: string) => apiDelete(target))

    // AI 流式对话：主进程消费 SSE，逐条转发给渲染层
    ipcMain.handle('chat:stream', async (event, message: string) => {
      const { status, port } = getSidecarInfo()
      if (status !== 'ok') return { ok: false, error: 'sidecar 未就绪' }
      try {
        const res = await fetch(`http://127.0.0.1:${port}/api/ai/chat/stream`, {
          method: 'POST',
          headers: {
            'x-api-key': getToken(),
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ message: String(message).slice(0, 8000) }),
          signal: AbortSignal.timeout(180000),
        })
        if (!res.ok || !res.body) {
          return { ok: false, error: `HTTP ${res.status}` }
        }
        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          let cut = buffer.indexOf('\n\n')
          while (cut >= 0) {
            const block = buffer.slice(0, cut).trim()
            buffer = buffer.slice(cut + 2)
            if (block.startsWith('data:')) {
              try {
                const payload = JSON.parse(block.slice(5).trim())
                event.sender.send('chat:event', payload)
              } catch {
                // 半截 JSON 丢弃，等下一个分片
              }
            }
            cut = buffer.indexOf('\n\n')
          }
        }
        return { ok: true }
      } catch (err) {
        return { ok: false, error: (err as Error).message }
      }
    })
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
        const tabArg = argValue('--shot-tab=')
        if (tabArg && /^[a-z-]+$/.test(tabArg)) {
          await win!.webContents.executeJavaScript(
            `document.querySelector('[data-tab="${tabArg}"]')?.click()`,
          )
          await new Promise((r) => setTimeout(r, 1500))
          const rowArg = argValue('--shot-row=')
          if (rowArg !== undefined) {
            const needle = JSON.stringify(rowArg)
            await win!.webContents.executeJavaScript(
              `([...document.querySelectorAll('.item')]
                 .find((el) => el.textContent.includes(${needle}))
                 || document.querySelector('.item'))?.click()`,
            )
            await new Promise((r) => setTimeout(r, 900))
          }
          const scanArg = argValue('--shot-scan=')
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

          // 截图前把 Markdown 示例滚到视口中央（组件页内容较长）
          if (process.argv.includes('--shot-scroll-md')) {
            const scrolled = await win!.webContents.executeJavaScript(`
              (() => {
                const el = document.querySelector('[data-md-sample]')
                if (!el) return 'no-element'
                el.scrollIntoView({ block: 'center' })
                window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 120)
                return Math.round(window.scrollY)
              })()
            `)
            console.log(`[shot] scrollY=${scrolled}`)
            await new Promise((r) => setTimeout(r, 600))
          }

          // 触发一次对话（用建议词填充后发送），用于截图验证流式链路
          if (process.argv.includes('--shot-chat')) {
            await win!.webContents.executeJavaScript(
              `document.querySelector('[data-suggest]')?.click()`,
            )
            await new Promise((r) => setTimeout(r, 300))
            await win!.webContents.executeJavaScript(
              `document.querySelector('[data-send]')?.click()`,
            )
            await new Promise((r) => setTimeout(r, 6000))
          }

          // 通用点击（选择器不能含空格，否则会被命令行拆开）
          const clickArg = argValue('--shot-click=')
          if (clickArg) {
            const found = await win!.webContents.executeJavaScript(
              `!!document.querySelector(${JSON.stringify(clickArg)})`,
            )
            console.log(`[shot] click ${clickArg} found=${found}`)
            await win!.webContents.executeJavaScript(
              `document.querySelector(${JSON.stringify(clickArg)})?.click()`,
            )
            await new Promise((r) => setTimeout(r, 1200))
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
