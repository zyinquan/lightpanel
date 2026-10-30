import { describe, expect, it, vi } from 'vitest'
import { nextTick, ref } from 'vue'
import { usePolling } from '@/composables/usePolling'
import { clearToasts, dismissToast, errorMessage, pushToast, useToast } from '@/composables/useToast'

describe('usePolling', () => {
  it('立即加载一次并暴露数据', async () => {
    const fetcher = vi.fn().mockResolvedValue({ cpu: 12 })
    const polling = usePolling(fetcher, { interval: 0 })

    await polling.refresh()
    expect(fetcher).toHaveBeenCalled()
    expect(polling.data.value).toEqual({ cpu: 12 })
    expect(polling.lastUpdated.value).toBeInstanceOf(Date)
    polling.stop()
  })

  it('失败时记录 error 并触发回调', async () => {
    const onError = vi.fn()
    const fetcher = vi.fn().mockRejectedValue(new Error('boom'))
    const polling = usePolling(fetcher, { interval: 0, onError })

    await polling.refresh()
    expect(polling.error.value).toBeInstanceOf(Error)
    expect(polling.data.value).toBeNull()
    expect(onError).toHaveBeenCalledTimes(1)
    polling.stop()
  })

  it('enabled 为 false 时轮询不再取数', async () => {
    vi.useFakeTimers()
    const fetcher = vi.fn().mockResolvedValue(1)
    const enabled = ref(false)
    const polling = usePolling(fetcher, { interval: 10, enabled })

    const callsAfterInit = fetcher.mock.calls.length
    await vi.advanceTimersByTimeAsync(100)
    expect(fetcher.mock.calls.length).toBe(callsAfterInit)

    enabled.value = true
    await vi.advanceTimersByTimeAsync(100)
    expect(fetcher.mock.calls.length).toBeGreaterThan(callsAfterInit)

    polling.stop()
    vi.useRealTimers()
  })

  it('并发的 refresh 会复用同一个请求', async () => {
    let resolve: (value: number) => void = () => {}
    const fetcher = vi.fn(
      () =>
        new Promise<number>((r) => {
          resolve = r
        }),
    )
    const polling = usePolling(fetcher, { interval: 0, immediate: false })

    const first = polling.refresh()
    const second = polling.refresh()
    resolve(42)
    await Promise.all([first, second])
    expect(fetcher).toHaveBeenCalledTimes(1)
    polling.stop()
  })
})

describe('useToast', () => {
  it('推入消息后可关闭与清空', async () => {
    clearToasts()
    const toast = useToast()
    const id = toast.success('保存成功')

    await nextTick()
    expect(toast.toasts.value).toHaveLength(1)
    expect(toast.toasts.value[0].message).toBe('保存成功')

    dismissToast(id)
    await nextTick()
    expect(toast.toasts.value).toHaveLength(0)

    pushToast('a')
    pushToast('b')
    clearToasts()
    await nextTick()
    expect(toast.toasts.value).toHaveLength(0)
  })

  it('errorMessage 能从异常中取到文案', () => {
    expect(errorMessage(new Error('炸了'))).toBe('炸了')
    expect(errorMessage('字符串错误')).toBe('字符串错误')
    expect(errorMessage(undefined)).toBe('未知错误')
  })
})
