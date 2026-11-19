import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('api', {
  health: () => ipcRenderer.invoke('app:health'),
  get: (path: string) => ipcRenderer.invoke('api:get', path),
})
