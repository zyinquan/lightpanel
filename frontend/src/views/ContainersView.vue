<script setup lang="ts">
import { computed, ref } from 'vue'
import { api } from '@/api/client'
import type { CommandDefinition, ContainerInfo, ContainerUsage } from '@/api/types'
import { usePolling } from '@/composables/usePolling'
import { errorMessage, pushToast } from '@/composables/useToast'
import ContainerCard from '@/components/ContainerCard.vue'
import CommandRunner from '@/components/CommandRunner.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import EmptyState from '@/components/EmptyState.vue'
import { stateLabel } from '@/utils/format'

const search = ref('')
const stateFilter = ref('')
const includeStopped = ref(true)

const containers = usePolling(
  () => api.containers({ search: search.value, state: stateFilter.value, includeStopped: includeStopped.value }),
  { interval: 5000 },
)
const commands = usePolling(() => api.commands('container'), { interval: 30000 })
const engine = usePolling(() => api.dockerStatus(), { interval: 15000 })
// 占用单独拉：stats 要等 daemon 采样一个周期，不能拖慢容器列表本身
const usage = usePolling(() => api.containerUsage(), { interval: 8000 })
const usageById = computed(() => {
  const map: Record<string, ContainerUsage> = {}
  for (const item of usage.data.value?.items ?? []) map[item.container_id] = item
  return map
})

const customCommands = computed(() => (commands.data.value ?? []).filter((c) => !c.builtin))
const busyIds = ref<Record<string, boolean>>({})

const runnerCommand = ref<CommandDefinition | null>(null)
const runnerTarget = ref('')
const runnerTargetLabel = ref('')
const runnerOpen = computed({
  get: () => runnerCommand.value !== null,
  set: (value: boolean) => {
    if (!value) runnerCommand.value = null
  },
})

function openCommand(command: CommandDefinition, container: ContainerInfo) {
  runnerCommand.value = command
  runnerTarget.value = container.id
  runnerTargetLabel.value = container.name
}

async function act(container: ContainerInfo, action: string) {
  busyIds.value = { ...busyIds.value, [container.id]: true }
  try {
    await api.containerAction(container.id, action as 'start')
    pushToast(`${container.name} ${stateLabel(action === 'start' ? 'running' : action)}成功`, 'success')
    await containers.refresh()
  } catch (error) {
    pushToast(errorMessage(error), 'error')
  } finally {
    const next = { ...busyIds.value }
    delete next[container.id]
    busyIds.value = next
  }
}

// ---- 日志 ------------------------------------------------------------------
const logsOpen = ref(false)
const logsTitle = ref('')
const logsContent = ref('')
const logsLoading = ref(false)

async function openLogs(container: ContainerInfo) {
  logsOpen.value = true
  logsTitle.value = container.name
  logsLoading.value = true
  logsContent.value = ''
  try {
    const payload = await api.containerLogs(container.id, 300)
    logsContent.value = payload.content || '(无日志输出)'
  } catch (error) {
    logsContent.value = errorMessage(error)
  } finally {
    logsLoading.value = false
  }
}

// ---- 删除确认 --------------------------------------------------------------
const pendingRemove = ref<ContainerInfo | null>(null)

async function confirmRemove() {
  const target = pendingRemove.value
  if (!target) return
  busyIds.value = { ...busyIds.value, [target.id]: true }
  try {
    await api.containerAction(target.id, 'remove')
    pushToast(`${target.name} 已删除`, 'success')
    await containers.refresh()
  } catch (error) {
    pushToast(errorMessage(error), 'error')
  } finally {
    pendingRemove.value = null
    const next = { ...busyIds.value }
    delete next[target.id]
    busyIds.value = next
  }
}

function requestAction(container: ContainerInfo, action: string) {
  if (action === 'remove') {
    pendingRemove.value = container
    return
  }
  void act(container, action)
}
</script>

<template>
  <section>
    <header class="bar">
      <input v-model="search" class="input bar__search" placeholder="搜索容器名称或镜像…" />
      <select v-model="stateFilter" class="select">
        <option value="">全部状态</option>
        <option value="running">运行中</option>
        <option value="exited">已停止</option>
        <option value="paused">已暂停</option>
      </select>
      <label class="bar__check">
        <input v-model="includeStopped" type="checkbox" />
        <span>包含已停止</span>
      </label>
      <span class="spacer" />
      <span class="dim">
        {{ engine.data.value?.available ? `引擎 ${engine.data.value.provider}` : '引擎不可用' }}
      </span>
      <button class="btn" :disabled="containers.loading.value" @click="containers.refresh()">
        刷新
      </button>
    </header>

    <div v-if="(containers.data.value?.length ?? 0) > 0" class="list">
      <ContainerCard
        v-for="container in containers.data.value ?? []"
        :key="container.id"
        :container="container"
        :usage="usageById[container.id]"
        :commands="customCommands"
        :busy="busyIds[container.id]"
        @action="requestAction(container, $event)"
        @command="openCommand($event, container)"
        @logs="openLogs"
      />
    </div>
    <EmptyState
      v-else
      title="没有容器"
      :description="
        engine.data.value && !engine.data.value.available
          ? 'Docker 引擎不可用，请检查套接字挂载与权限。'
          : '当前没有匹配的容器。'
      "
    />

    <CommandRunner
      :open="runnerOpen"
      :command="runnerCommand"
      :target-id="runnerTarget"
      :target-label="runnerTargetLabel"
      @close="runnerCommand = null"
      @executed="containers.refresh()"
    />

    <!-- 日志抽屉 -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="logsOpen" class="mask" @click.self="logsOpen = false">
          <div class="logs card">
            <header class="logs__head">
              <h3>{{ logsTitle }} 日志</h3>
              <button class="btn btn--ghost btn--sm" @click="logsOpen = false">✕</button>
            </header>
            <pre class="logs__body mono">{{ logsLoading ? '加载中…' : logsContent }}</pre>
          </div>
        </div>
      </Transition>
    </Teleport>

    <ConfirmDialog
      :open="!!pendingRemove"
      title="删除容器"
      :message="`确定删除容器「${pendingRemove?.name ?? ''}」？该操作会移除容器实例。`"
      danger
      :expect-text="pendingRemove?.name ?? ''"
      confirm-text="删除"
      @cancel="pendingRemove = null"
      @confirm="confirmRemove"
    />
  </section>
</template>

<style scoped>
.bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.bar__search {
  width: min(280px, 60vw);
}

.bar__check {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  color: var(--text-muted);
}

.list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(330px, 1fr));
  gap: 12px;
}

.mask {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: grid;
  place-items: center;
  background: rgba(0, 0, 0, 0.55);
}

.logs {
  width: min(860px, 94vw);
  padding: 16px;
  box-shadow: var(--shadow);
}

.logs__head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.logs__head h3 {
  font-size: 15px;
}

.logs__body {
  margin: 0;
  max-height: 60vh;
  overflow: auto;
  padding: 12px;
  background: #0b1017;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 12px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
