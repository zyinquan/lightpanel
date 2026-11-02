import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { StackInfo } from '@/api/types'

const mocks = vi.hoisted(() => ({
  stacks: vi.fn(),
  commands: vi.fn(),
  stackAction: vi.fn(),
}))

vi.mock('@/api/client', () => ({
  api: {
    stacks: mocks.stacks,
    commands: mocks.commands,
    stackAction: mocks.stackAction,
  },
}))

import StacksView from '@/views/StacksView.vue'

function stack(name: string): StackInfo {
  return {
    name,
    config_files: `E:\\dev\\${name}\\docker-compose.yml`,
    working_dir: `E:\\dev\\${name}`,
    status: 'running',
    discovered_paths: [],
    containers: [],
    running: 1,
    total: 1,
  }
}

describe('StacksView', () => {
  it('代理不可用时给出原因，而不是谎称「没有编排栈」', async () => {
    mocks.stacks.mockRejectedValue(
      new Error('连不上宿主机代理（All connection attempts failed），请确认已启动 lightpanel-agent'),
    )
    mocks.commands.mockResolvedValue([])

    const wrapper = mount(StacksView)
    await flushPromises()

    const banner = wrapper.find('[data-test="stacks-error"]')
    expect(banner.exists()).toBe(true)
    expect(banner.text()).toContain('栈列表不可用')
    expect(banner.text()).toContain('lightpanel-agent')
    // 空态会让人以为目录里没有项目，这里必须让位给错误提示
    expect(wrapper.text()).not.toContain('没有编排栈')
  })

  it('拿到栈列表时正常渲染卡片', async () => {
    mocks.stacks.mockResolvedValue([stack('devdemo')])
    mocks.commands.mockResolvedValue([])

    const wrapper = mount(StacksView)
    await flushPromises()

    expect(wrapper.find('[data-test="stacks-error"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('devdemo')
  })
})
