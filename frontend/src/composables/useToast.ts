/** 全局轻量提示：模块级单例，任何组件都可推入消息。 */

import { readonly, ref } from 'vue'

export type ToastKind = 'success' | 'error' | 'info' | 'warning'

export interface Toast {
  id: number
  kind: ToastKind
  message: string
  /** 毫秒；0 表示不自动消失。 */
  duration: number
}

const toasts = ref<Toast[]>([])
let counter = 0

const DEFAULT_DURATION: Record<ToastKind, number> = {
  success: 2600,
  info: 2600,
  warning: 4000,
  error: 5200,
}

export function pushToast(message: string, kind: ToastKind = 'info', duration?: number): number {
  counter += 1
  const id = counter
  const lifetime = duration ?? DEFAULT_DURATION[kind]
  toasts.value = [...toasts.value, { id, kind, message, duration: lifetime }]
  if (lifetime > 0) {
    setTimeout(() => dismissToast(id), lifetime)
  }
  return id
}

export function dismissToast(id: number): void {
  toasts.value = toasts.value.filter((t) => t.id !== id)
}

export function clearToasts(): void {
  toasts.value = []
}

export function useToast() {
  return {
    toasts: readonly(toasts),
    success: (msg: string) => pushToast(msg, 'success'),
    error: (msg: string) => pushToast(msg, 'error'),
    info: (msg: string) => pushToast(msg, 'info'),
    warning: (msg: string) => pushToast(msg, 'warning'),
    dismiss: dismissToast,
    clear: clearToasts,
  }
}

/** 把任意异常转成可展示文案。 */
export function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  if (typeof error === 'string') return error
  return '未知错误'
}
