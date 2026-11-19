import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('api', {
  health: () => ipcRenderer.invoke('app:health'),
  get: (path: string) => ipcRenderer.invoke('api:get', path),
  post: (path: string, body?: unknown) => ipcRenderer.invoke('api:post', path, body),
  del: (path: string) => ipcRenderer.invoke('api:delete', path),
  open: (path: string) => ipcRenderer.invoke('shell:open', path),
  openExternal: (url: string) => ipcRenderer.invoke('shell:openExternal', url),
  reveal: (path: string) => ipcRenderer.invoke('shell:reveal', path),
  copy: (text: string) => ipcRenderer.invoke('clipboard:write', text),
  thumb: (path: string, size?: number) => ipcRenderer.invoke('api:thumb', path, size),
  readText: (path: string) => ipcRenderer.invoke('file:readText', path),
  pickDirectory: () => ipcRenderer.invoke('dialog:pickDirectory'),
  confirm: (title: string, message: string) =>
    ipcRenderer.invoke('dialog:confirm', title, message),
  chatStream: (message: string) => ipcRenderer.invoke('chat:stream', message),
  onChatEvent: (handler: (payload: any) => void) => {
    const listener = (_event: unknown, payload: any) => handler(payload)
    ipcRenderer.on('chat:event', listener)
    return () => ipcRenderer.removeListener('chat:event', listener)
  },
})
