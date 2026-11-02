import { describe, expect, it } from 'vitest'
import {
  colorFromString,
  formatBytes,
  formatDateTime,
  formatDuration,
  formatPercent,
  initials,
  normalizeUrl,
  stateColor,
  stateLabel,
  usageColor,
} from '@/utils/format'

describe('formatBytes', () => {
  it('以 1024 为进制换算并保留一位小数', () => {
    expect(formatBytes(0)).toBe('0 B')
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(1024)).toBe('1.0 KB')
    expect(formatBytes(1536)).toBe('1.5 KB')
    expect(formatBytes(1024 ** 3)).toBe('1.0 GB')
  })

  it('对非法输入返回占位符', () => {
    expect(formatBytes(Number.NaN)).toBe('-')
    expect(formatBytes(-1)).toBe('-')
  })
})

describe('formatDuration', () => {
  it('按量级切换单位', () => {
    expect(formatDuration(45)).toBe('45秒')
    expect(formatDuration(90)).toBe('1分 30秒')
    expect(formatDuration(3600 * 2 + 60)).toBe('2小时 1分')
    expect(formatDuration(86400 * 3 + 3600)).toBe('3天 1小时')
  })

  it('负数按 0 处理', () => {
    expect(formatDuration(-5)).toBe('0秒')
  })
})

describe('formatPercent / formatDateTime', () => {
  it('百分比默认一位小数', () => {
    expect(formatPercent(12.345)).toBe('12.3%')
    expect(formatPercent(Number.NaN)).toBe('-')
  })

  it('日期时间补零', () => {
    expect(formatDateTime(new Date(2026, 0, 2, 3, 4, 5))).toBe('2026-01-02 03:04:05')
    expect(formatDateTime('')).toBe('-')
    expect(formatDateTime(null)).toBe('-')
    expect(formatDateTime('not-a-date')).toBe('-')
  })
})

describe('usageColor', () => {
  it('按阈值返回语义色', () => {
    expect(usageColor(10)).toBe('var(--success)')
    expect(usageColor(80)).toBe('var(--warning)')
    expect(usageColor(95)).toBe('var(--danger)')
  })
})

describe('state 映射', () => {
  it('容器状态有中文标签', () => {
    expect(stateLabel('running')).toBe('运行中')
    expect(stateLabel('exited')).toBe('已停止')
    expect(stateLabel('weird')).toBe('weird')
  })

  it('状态色可区分', () => {
    expect(stateColor('running')).toBe('var(--success)')
    expect(stateColor('exited')).not.toBe(stateColor('running'))
  })
})

describe('colorFromString / initials', () => {
  it('同一输入稳定派生同一颜色', () => {
    expect(colorFromString('jellyfin')).toBe(colorFromString('jellyfin'))
    expect(colorFromString('jellyfin')).not.toBe(colorFromString('plex'))
    expect(colorFromString('x')).toMatch(/^hsl\(\d+, 62%, 58%\)$/)
  })

  it('取首字母或前两个字母', () => {
    expect(initials('Jellyfin')).toBe('JE')
    expect(initials('影音')).toBe('影')
    expect(initials('  ')).toBe('?')
  })
})

describe('normalizeUrl', () => {
  it('保留已有协议', () => {
    expect(normalizeUrl('http://nas:8096')).toBe('http://nas:8096')
    expect(normalizeUrl('https://example.com/a?b=1')).toBe('https://example.com/a?b=1')
  })

  it('缺协议时补 http://，避免被当成相对路径', () => {
    expect(normalizeUrl('nas:8096')).toBe('http://nas:8096')
    expect(normalizeUrl('192.168.1.2:5001')).toBe('http://192.168.1.2:5001')
    expect(normalizeUrl('//nas:8096/x')).toBe('http://nas:8096/x')
    expect(normalizeUrl('  docker.local  ')).toBe('http://docker.local')
  })

  it('空值与危险协议不可跳转', () => {
    expect(normalizeUrl('')).toBe('')
    expect(normalizeUrl(undefined)).toBe('')
    expect(normalizeUrl('javascript:alert(1)')).toBe('')
    expect(normalizeUrl('data:text/html,<b>x')).toBe('')
  })
})
