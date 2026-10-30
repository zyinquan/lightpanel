import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import SoftwareCard from '@/components/SoftwareCard.vue'
import ContainerCard from '@/components/ContainerCard.vue'
import StackCard from '@/components/StackCard.vue'
import TagFilter from '@/components/TagFilter.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import type { CommandDefinition, ContainerInfo, SoftwareEntry, StackInfo } from '@/api/types'

const entry: SoftwareEntry = {
  id: 'jellyfin',
  name: 'Jellyfin',
  url: 'http://nas:8096',
  description: '影音库',
  icon: '',
  color: '#ff5c8a',
  category: '影音',
  tags: ['影音', '自建'],
  enabled: true,
  order: 0,
}

const container: ContainerInfo = {
  id: 'abc123456789',
  short_id: 'abc123',
  name: 'nginx',
  image: 'nginx:1.27',
  state: 'running',
  status: 'Up 2 hours',
  created_at: '2026-01-01T00:00:00Z',
  ports: ['0.0.0.0:80->80/tcp'],
  labels: {},
  compose_project: 'web',
  compose_service: 'nginx',
}

const stack: StackInfo = {
  name: 'blog',
  config_files: '/opt/blog/docker-compose.yml',
  working_dir: '/opt/blog',
  status: 'running',
  discovered_paths: ['/opt/blog'],
  containers: [container],
  running: 1,
  total: 1,
}

const customCommand: CommandDefinition = {
  id: 'container.logs.follow',
  name: '跟踪日志',
  target: 'container',
  kind: 'shell',
  action: 'logs',
  argv: ['docker', 'logs', '-f', '{id}'],
  description: '实时跟踪',
  confirm: false,
  danger: false,
  timeout: 60,
  working_dir: null,
  builtin: false,
}

describe('SoftwareCard', () => {
  it('渲染名称、描述、跳转链接与标签', () => {
    const wrapper = mount(SoftwareCard, { props: { entry } })
    expect(wrapper.text()).toContain('Jellyfin')
    expect(wrapper.text()).toContain('影音库')
    expect(wrapper.get('a').attributes('href')).toBe('http://nas:8096')
    expect(wrapper.findAll('.chip--tag')).toHaveLength(2)
  })

  it('点击标签派发 tag 事件', async () => {
    const wrapper = mount(SoftwareCard, { props: { entry } })
    await wrapper.findAll('.chip--tag')[0].trigger('click')
    expect(wrapper.emitted('tag')?.[0]).toEqual(['影音'])
  })

  it('编辑与删除按钮分别派发事件', async () => {
    const wrapper = mount(SoftwareCard, { props: { entry } })
    const buttons = wrapper.findAll('.software__actions .btn')
    await buttons[0].trigger('click')
    await buttons[1].trigger('click')
    expect(wrapper.emitted('edit')?.[0]).toEqual([entry])
    expect(wrapper.emitted('remove')?.[0]).toEqual([entry])
  })

  it('已选中的标签高亮', () => {
    const wrapper = mount(SoftwareCard, { props: { entry, activeTags: ['自建'] } })
    const chips = wrapper.findAll('.chip--tag')
    expect(chips[0].classes()).not.toContain('chip--active')
    expect(chips[1].classes()).toContain('chip--active')
  })
})

describe('ContainerCard', () => {
  it('运行中容器给出 重启/停止/暂停 操作', () => {
    const wrapper = mount(ContainerCard, { props: { container } })
    const labels = wrapper.findAll('.container__actions .btn').map((b) => b.text())
    expect(labels).toEqual(['重启', '停止', '暂停', '日志'])
  })

  it('已停止容器给出 启动/删除 操作', () => {
    const wrapper = mount(ContainerCard, {
      props: { container: { ...container, state: 'exited' } },
    })
    const labels = wrapper.findAll('.container__actions .btn').map((b) => b.text())
    expect(labels).toEqual(['启动', '删除', '日志'])
  })

  it('点击操作按钮派发 action', async () => {
    const wrapper = mount(ContainerCard, { props: { container } })
    await wrapper.findAll('.container__actions .btn')[1].trigger('click')
    expect(wrapper.emitted('action')?.[0]).toEqual(['stop'])
  })

  it('渲染自定义命令按钮并派发 command', async () => {
    const wrapper = mount(ContainerCard, { props: { container, commands: [customCommand] } })
    const button = wrapper.findAll('.container__actions .btn').at(-1)
    expect(button?.text()).toBe('跟踪日志')
    await button?.trigger('click')
    expect(wrapper.emitted('command')?.[0]).toEqual([customCommand])
  })

  it('busy 时禁用所有按钮', () => {
    const wrapper = mount(ContainerCard, { props: { container, busy: true } })
    expect(wrapper.findAll('.container__actions .btn').every((b) => b.attributes('disabled') !== undefined)).toBe(true)
  })

  it('展示镜像与 compose 归属', () => {
    const wrapper = mount(ContainerCard, { props: { container } })
    expect(wrapper.text()).toContain('nginx:1.27')
    expect(wrapper.text()).toContain('web/nginx')
  })
})

describe('StackCard', () => {
  it('展示栈名、路径与运行比例', () => {
    const wrapper = mount(StackCard, { props: { stack } })
    expect(wrapper.text()).toContain('blog')
    expect(wrapper.text()).toContain('/opt/blog/docker-compose.yml')
    expect(wrapper.text()).toContain('1/1')
  })

  it('点击动作按钮派发 action', async () => {
    const wrapper = mount(StackCard, { props: { stack } })
    const buttons = wrapper.findAll('.stack__actions .btn')
    expect(buttons.map((b) => b.text())).toEqual(['启动', '停止', '重启', '拉取', '构建'])
    await buttons[1].trigger('click')
    expect(wrapper.emitted('action')?.[0]).toEqual(['down'])
  })

  it('展开后列出成员容器', () => {
    const wrapper = mount(StackCard, { props: { stack, expanded: true } })
    expect(wrapper.find('.stack__containers').exists()).toBe(true)
    expect(wrapper.text()).toContain('nginx')
  })
})

describe('TagFilter', () => {
  const tags = [
    { name: '影音', count: 3 },
    { name: '自建', count: 1 },
  ]

  it('渲染全部与标签计数', () => {
    const wrapper = mount(TagFilter, { props: { tags, selected: [] } })
    expect(wrapper.text()).toContain('全部')
    expect(wrapper.text()).toContain('影音')
    expect(wrapper.text()).toContain('3')
  })

  it('点击标签与清空分别派发 toggle / clear', async () => {
    const wrapper = mount(TagFilter, { props: { tags, selected: [] } })
    const chips = wrapper.findAll('.chip')
    await chips[1].trigger('click')
    expect(wrapper.emitted('toggle')?.[0]).toEqual(['影音'])
    await chips[0].trigger('click')
    expect(wrapper.emitted('clear')).toHaveLength(1)
  })

  it('选中多个标签时才显示“同时满足”开关', async () => {
    const single = mount(TagFilter, { props: { tags, selected: ['影音'] } })
    expect(single.find('.tagfilter__match').exists()).toBe(false)

    const multi = mount(TagFilter, { props: { tags, selected: ['影音', '自建'], matchAll: true } })
    expect(multi.find('.tagfilter__match').exists()).toBe(true)
    await multi.find('.tagfilter__match input').setValue(false)
    expect(multi.emitted('update:matchAll')?.[0]).toEqual([false])
  })
})

describe('ConfirmDialog', () => {
  // 对话框通过 Teleport 挂到 body，测试中把它 stub 在原地以便查询。
  const mountDialog = (props: { open: boolean; title?: string; expectText?: string }) =>
    mount(ConfirmDialog, { props, global: { stubs: { Teleport: true } } })

  it('未开启时不渲染', () => {
    const wrapper = mountDialog({ open: false })
    expect(wrapper.find('.dialog').exists()).toBe(false)
  })

  it('普通确认直接可点', async () => {
    const wrapper = mountDialog({ open: true, title: '删除' })
    const buttons = wrapper.findAll('.dialog__actions .btn')
    expect((buttons[1].element as HTMLButtonElement).disabled).toBe(false)
    await buttons[1].trigger('click')
    expect(wrapper.emitted('confirm')).toHaveLength(1)
  })

  it('需要输入校验文本时，输入不匹配则禁止确认', async () => {
    const wrapper = mountDialog({ open: true, title: '删除容器', expectText: 'nginx' })
    const confirmButton = () => wrapper.findAll('.dialog__actions .btn')[1]
    expect((confirmButton().element as HTMLButtonElement).disabled).toBe(true)

    await wrapper.find('.dialog__input').setValue('ngin')
    expect((confirmButton().element as HTMLButtonElement).disabled).toBe(true)
    expect(wrapper.emitted('confirm')).toBeUndefined()

    await wrapper.find('.dialog__input').setValue('nginx')
    expect((confirmButton().element as HTMLButtonElement).disabled).toBe(false)
    await confirmButton().trigger('click')
    expect(wrapper.emitted('confirm')).toHaveLength(1)
  })

  it('取消按钮派发 cancel', async () => {
    const wrapper = mountDialog({ open: true })
    await wrapper.findAll('.dialog__actions .btn')[0].trigger('click')
    expect(wrapper.emitted('cancel')).toHaveLength(1)
  })
})
