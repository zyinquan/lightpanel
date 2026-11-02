import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { SystemSnapshot } from '@/api/types'

const mocks = vi.hoisted(() => ({
  system: vi.fn(),
  systemHistory: vi.fn(),
  containers: vi.fn(),
  stacks: vi.fn(),
}))

vi.mock('@/api/client', () => ({
  api: {
    system: mocks.system,
    systemHistory: mocks.systemHistory,
    containers: mocks.containers,
    stacks: mocks.stacks,
  },
}))

import DashboardView from '@/views/DashboardView.vue'

function snapshot(scope: 'host' | 'container', hint: string | null): SystemSnapshot {
  return {
    host: {
      hostname: scope === 'host' ? 'DESKTOP-ABC' : '8c04c9ba5444',
      os_name: 'Windows',
      os_version: '11',
      arch: 'AMD64',
      boot_time: 1_700_000_000,
      uptime_seconds: 3600,
      uptime_human: '1小时 0分',
    },
    cpu: {
      percent: 12,
      logical_count: 16,
      physical_count: 8,
      per_cpu: [],
      load_average: [1, 0.5, 0.2],
      frequency_mhz: 3600,
    },
    memory: {
      total: 34_359_738_368,
      used: 17_179_869_184,
      available: 17_179_869_184,
      percent: 50,
      total_human: '32.0 GB',
      used_human: '16.0 GB',
      swap_total: 0,
      swap_used: 0,
      swap_percent: 0,
    },
    disks: [],
    network: null,
    collected_at: '2026-11-01T12:00:00Z',
    scope,
    source: scope === 'host' ? 'agent' : 'psutil',
    hint,
  }
}

async function mountWith(payload: SystemSnapshot) {
  mocks.system.mockResolvedValue(payload)
  mocks.systemHistory.mockResolvedValue([])
  mocks.containers.mockResolvedValue([])
  mocks.stacks.mockResolvedValue([])
  const wrapper = mount(DashboardView)
  await flushPromises()
  return wrapper
}

describe('DashboardView 指标口径', () => {
  it('宿主机指标时标明来源与主机名', async () => {
    const wrapper = await mountWith(snapshot('host', null))
    const scope = wrapper.get('[data-test="scope"]')
    expect(scope.text()).toContain('宿主机指标')
    expect(scope.text()).toContain('DESKTOP-ABC')
    expect(scope.text()).toContain('宿主机代理')
    expect(scope.classes()).toContain('scope--host')
  })

  it('容器内指标时给出提示，避免误读成宿主机', async () => {
    const hint = '面板运行在容器内，指标来自容器（或 Docker 虚拟机），并非宿主机。'
    const wrapper = await mountWith(snapshot('container', hint))
    const scope = wrapper.get('[data-test="scope"]')
    expect(scope.text()).toContain('容器内指标')
    expect(scope.text()).toContain('并非宿主机')
    expect(scope.classes()).toContain('scope--container')
  })
})
