/// <reference types="vite/client" />

interface SidecarInfo {
  status: 'starting' | 'ok' | 'failed'
  port: number
  version?: string
  pid?: number
  error?: string
}

interface ApiResult {
  ok: boolean
  status: number
  data?: unknown
  error?: string
}

declare global {
  interface Window {
    api: {
      health: () => Promise<SidecarInfo>
      get: (path: string) => Promise<ApiResult>
      post: (path: string, body?: unknown) => Promise<ApiResult>
      del: (path: string) => Promise<ApiResult>
      open: (path: string) => Promise<string>
      openExternal: (url: string) => Promise<boolean>
      openDataDir: () => Promise<string>
      chatStream: (message: string) => Promise<{ ok: boolean; error?: string }>
      onChatEvent: (handler: (payload: any) => void) => () => void
      reveal: (path: string) => Promise<void>
      copy: (text: string) => Promise<void>
      thumb: (path: string, size?: number) => Promise<ApiResult>
      readText: (path: string) => Promise<{ ok: boolean; data?: string; error?: string }>
      pickDirectory: () => Promise<string>
      confirm: (title: string, message: string) => Promise<boolean>
    }
  }
}

export {}
