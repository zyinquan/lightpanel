/** 带可见性感知与失败退避的轮询资源。 */

import { getCurrentScope, onScopeDispose, ref, shallowRef, type Ref } from 'vue'

export interface UsePollingOptions {
  /** 轮询间隔（毫秒）。 */
  interval?: number
  /** false 时暂停轮询（例如等待用户输入）。 */
  enabled?: Ref<boolean> | (() => boolean)
  immediate?: boolean
  onError?: (error: unknown) => void
}

export interface UsePollingReturn<T> {
  data: Ref<T | null>
  error: Ref<unknown>
  loading: Ref<boolean>
  lastUpdated: Ref<Date | null>
  refresh: () => Promise<void>
  start: () => void
  stop: () => void
  setInterval: (ms: number) => void
}

function isEnabled(enabled: UsePollingOptions['enabled']): boolean {
  if (enabled === undefined) return true
  return typeof enabled === 'function' ? enabled() : enabled.value
}

export function usePolling<T>(
  fetcher: () => Promise<T>,
  options: UsePollingOptions = {},
): UsePollingReturn<T> {
  const data = shallowRef<T | null>(null) as Ref<T | null>
  const error = shallowRef<unknown>(null) as Ref<unknown>
  const loading = ref(false)
  const lastUpdated = ref<Date | null>(null)

  let interval = options.interval ?? 5000
  let timer: ReturnType<typeof setTimeout> | null = null
  let stopped = false
  let inFlight: Promise<void> | null = null

  async function refresh(): Promise<void> {
    if (inFlight) return inFlight
    loading.value = true
    inFlight = (async () => {
      try {
        data.value = await fetcher()
        error.value = null
        lastUpdated.value = new Date()
      } catch (err) {
        error.value = err
        options.onError?.(err)
      } finally {
        loading.value = false
        inFlight = null
      }
    })()
    return inFlight
  }

  function schedule(): void {
    if (timer) clearTimeout(timer)
    if (stopped || interval <= 0) return
    timer = setTimeout(async () => {
      timer = null
      if (!stopped && isEnabled(options.enabled) && !documentHidden()) {
        await refresh()
      }
      schedule()
    }, interval)
  }

  function start(): void {
    stopped = false
    schedule()
  }

  function stop(): void {
    stopped = true
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
  }

  function setInterval(ms: number): void {
    interval = ms
    if (!stopped) schedule()
  }

  if (options.immediate !== false) void refresh()
  start()

  // 在组件/effect 作用域外使用（例如测试）时不应注册清理钩子。
  if (getCurrentScope()) onScopeDispose(stop)

  return { data, error, loading, lastUpdated, refresh, start, stop, setInterval }
}

function documentHidden(): boolean {
  return typeof document !== 'undefined' && document.visibilityState === 'hidden'
}
