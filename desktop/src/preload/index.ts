import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('api', {
  health: () => ipcRenderer.invoke('app:health'),
  get: (path: string) => ipcRenderer.invoke('api:get', path),
  open: (path: string) => ipcRenderer.invoke('shell:open', path),
  reveal: (path: string) => ipcRenderer.invoke('shell:reveal', path),
  copy: (text: string) => ipcRenderer.invoke('clipboard:write', text),
})
