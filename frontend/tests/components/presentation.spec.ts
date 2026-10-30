import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import UsageBar from '@/components/UsageBar.vue'
import StatCard from '@/components/StatCard.vue'
import SparkLine from '@/components/SparkLine.vue'
import EmptyState from '@/components/EmptyState.vue'
import OutputConsole from '@/components/OutputConsole.vue'
import type { CommandResult } from '@/api/types'

describe('UsageBar', () => {
  it('把百分比写进 aria 与宽度', () => {
    const wrapper = mount(UsageBar, { props: { percent: 42.5, label: 'CPU' } })
    const bar = wrapper.get('[role="progressbar"]')
    expect(bar.attributes('aria-valuenow')).toBe('43')
    expect((bar.element as HTMLElement).style.width).toBe('42.5%')
    expect(wrapper.text()).toContain('42.5%')
  })

  it('超过 100 或小于 0 会被夹紧', () => {
    const wrapper = mount(UsageBar, { props: { percent: 180 } })
    expect(wrapper.get('[role="progressbar"]').attributes('aria-valuenow')).toBe('100')
    const negative = mount(UsageBar, { props: { percent: -20 } })
    expect(negative.get('[role="progressbar"]').attributes('aria-valuenow')).toBe('0')
  })
})

describe('StatCard', () => {
  it('渲染标题、值与提示', () => {
    const wrapper = mount(StatCard, { props: { title: 'CPU', value: '31.2%', hint: '8 核' } })
    expect(wrapper.text()).toContain('CPU')
    expect(wrapper.text()).toContain('31.2%')
    expect(wrapper.text()).toContain('8 核')
  })

  it('支持插槽覆盖提示区', () => {
    const wrapper = mount(StatCard, {
      props: { title: '内存', value: '60%' },
      slots: { default: '<span class="spark" />' },
    })
    expect(wrapper.find('.spark').exists()).toBe(true)
  })
})

describe('SparkLine', () => {
  it('空数据退化为单个点而不抛错', () => {
    const wrapper = mount(SparkLine, { props: { values: [] } })
    expect(wrapper.find('polyline').attributes('points')).toBe('0,38')
  })

  it('按 max 缩放高度', () => {
    const wrapper = mount(SparkLine, { props: { values: [0, 50, 100], width: 100, height: 40 } })
    const points = wrapper.find('polyline').attributes('points')?.split(' ') ?? []
    expect(points).toHaveLength(3)
    const ys = points.map((p) => Number(p.split(',')[1]))
    expect(ys[0]).toBeGreaterThan(ys[2])
    expect(ys[2]).toBeCloseTo(2, 0)
  })
})

describe('EmptyState', () => {
  it('展示标题与描述', () => {
    const wrapper = mount(EmptyState, {
      props: { title: '暂无容器', description: '引擎不可用' },
    })
    expect(wrapper.text()).toContain('暂无容器')
    expect(wrapper.text()).toContain('引擎不可用')
  })
})

describe('OutputConsole', () => {
  const okResult: CommandResult = {
    ok: true,
    exit_code: 0,
    argv: ['docker', 'ps'],
    stdout: 'CONTAINER ID',
    stderr: '',
    duration_ms: 12,
  }

  it('成功结果显示退出码与命令', () => {
    const wrapper = mount(OutputConsole, { props: { result: okResult } })
    expect(wrapper.text()).toContain('exit 0')
    expect(wrapper.text()).toContain('$ docker ps')
    expect(wrapper.text()).toContain('CONTAINER ID')
  })

  it('stderr 会附加在 stdout 之后', () => {
    const wrapper = mount(OutputConsole, {
      props: { result: { ...okResult, ok: false, exit_code: 1, stdout: 'out', stderr: 'err' } },
    })
    expect(wrapper.text()).toContain('out')
    expect(wrapper.text()).toContain('--- stderr ---')
    expect(wrapper.text()).toContain('err')
  })

  it('无输出时给出占位文案', () => {
    const wrapper = mount(OutputConsole, {
      props: { result: { ...okResult, stdout: '', stderr: '' } },
    })
    expect(wrapper.text()).toContain('(无输出)')
  })

  it('result 为空时整块不渲染', () => {
    const wrapper = mount(OutputConsole, { props: { result: null } })
    expect(wrapper.find('.console').exists()).toBe(false)
  })
})
