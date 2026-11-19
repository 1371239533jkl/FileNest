/// <reference types="vite/client" />

interface SidecarInfo {
  status: 'starting' | 'ok' | 'failed'
  port: number
  version?: string
  pid?: number
  error?: string
}

declare global {
  interface Window {
    api: {
      health: () => Promise<SidecarInfo>
    }
  }
}

export {}
