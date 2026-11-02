/** 展示层格式化工具 —— 纯函数，便于单测。 */

const BYTE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'] as const

export function formatBytes(bytes: number, fractionDigits = 1): string {
  if (!Number.isFinite(bytes) || bytes < 0) return '-'
  let value = bytes
  let unitIndex = 0
  while (value >= 1024 && unitIndex < BYTE_UNITS.length - 1) {
    value /= 1024
    unitIndex += 1
  }
  const digits = unitIndex === 0 ? 0 : fractionDigits
  return `${value.toFixed(digits)} ${BYTE_UNITS[unitIndex]}`
}

export function formatPercent(value: number, digits = 1): string {
  if (!Number.isFinite(value)) return '-'
  return `${value.toFixed(digits)}%`
}

export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds))
  const days = Math.floor(total / 86400)
  const hours = Math.floor((total % 86400) / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const secs = total % 60
  if (days) return `${days}天 ${hours}小时`
  if (hours) return `${hours}小时 ${minutes}分`
  if (minutes) return `${minutes}分 ${secs}秒`
  return `${secs}秒`
}

export function formatDateTime(value: string | number | Date | null | undefined): string {
  if (value === null || value === undefined || value === '') return '-'
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

/** 依据百分比给出语义色：绿 → 黄 → 红。 */
export function usageColor(percent: number): string {
  if (percent >= 90) return 'var(--danger)'
  if (percent >= 75) return 'var(--warning)'
  return 'var(--success)'
}

export function stateColor(state: string): string {
  switch (state.toLowerCase()) {
    case 'running':
    case 'up':
      return 'var(--success)'
    case 'paused':
      return 'var(--warning)'
    case 'exited':
    case 'dead':
    case 'down':
      return 'var(--text-dim)'
    case 'restarting':
      return 'var(--accent)'
    default:
      return 'var(--text-muted)'
  }
}

export function stateLabel(state: string): string {
  switch (state.toLowerCase()) {
    case 'running':
      return '运行中'
    case 'exited':
      return '已停止'
    case 'created':
      return '已创建'
    case 'paused':
      return '已暂停'
    case 'restarting':
      return '重启中'
    case 'dead':
      return '异常'
    case 'up':
      return '已启动'
    case 'down':
      return '已停止'
    case 'partial':
      return '部分运行'
    case 'unknown':
      return '未知'
    default:
      return state
  }
}

/** 从任意字符串稳定派生一个 HSL 色，用于软件卡片配色。 */
export function colorFromString(input: string, saturation = 62, lightness = 58): string {
  let hash = 0
  for (let i = 0; i < input.length; i += 1) {
    hash = (hash * 31 + input.charCodeAt(i)) % 360000
  }
  return `hsl(${hash % 360}, ${saturation}%, ${lightness}%)`
}

/**
 * 归一化软件条目的跳转地址。
 *
 * 用户常常只填 `nas:8096` / `192.168.1.2:5001`，浏览器会把这种值当成**相对路径**
 * 拼到当前页面上，点开只会回到面板本身，看起来就是"没反应"。这里统一补齐协议；
 * 同时把 `javascript:` / `data:` 之类的危险协议直接判为不可用。
 */
export function normalizeUrl(raw: string | null | undefined): string {
  const value = (raw ?? '').trim()
  if (!value) return ''
  if (/^(javascript|data|vbscript|file):/i.test(value)) return ''
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(value)) return value
  return `http://${value.replace(/^\/+/, '')}`
}

export function initials(name: string): string {
  const cleaned = name.trim().replace(/[^\p{L}\p{N}]+/gu, ' ')
  const parts = cleaned.split(/\s+/).filter(Boolean)
  if (!parts.length) return '?'
  if (parts[0].match(/^[\u4e00-\u9fa5]/)) return parts[0].slice(0, 1)
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[1][0]).toUpperCase()
}
