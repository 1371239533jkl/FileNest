import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('api', {
  health: () => ipcRenderer.invoke('app:health'),
})
