import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('api', {
  health: () => ipcRenderer.invoke('app:health'),
  get: (path: string) => ipcRenderer.invoke('api:get', path),
  post: (path: string, body?: unknown) => ipcRenderer.invoke('api:post', path, body),
  open: (path: string) => ipcRenderer.invoke('shell:open', path),
  reveal: (path: string) => ipcRenderer.invoke('shell:reveal', path),
  copy: (text: string) => ipcRenderer.invoke('clipboard:write', text),
  thumb: (path: string, size?: number) => ipcRenderer.invoke('api:thumb', path, size),
  readText: (path: string) => ipcRenderer.invoke('file:readText', path),
  pickDirectory: () => ipcRenderer.invoke('dialog:pickDirectory'),
})
