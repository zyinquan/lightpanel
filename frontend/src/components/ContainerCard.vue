<script setup lang="ts">
import { computed } from 'vue'
import type { CommandDefinition, ContainerInfo } from '@/api/types'
import { formatDateTime, stateColor, stateLabel } from '@/utils/format'

const props = defineProps<{
  container: ContainerInfo
  commands?: CommandDefinition[]
  busy?: boolean
}>()

const emit = defineEmits<{
  action: [string]
  command: [CommandDefinition]
  logs: [ContainerInfo]
}>()

const isRunning = computed(() => props.container.state.toLowerCase() === 'running')
const isPaused = computed(() => props.container.state.toLowerCase() === 'paused')
const color = computed(() => stateColor(props.container.state))
const created = computed(() => formatDateTime(props.container.created_at))
const subtitle = computed(() => {
  const parts = [props.container.image]
  if (props.container.compose_project) {
    parts.push(
      props.container.compose_service
        ? `${props.container.compose_project}/${props.container.compose_service}`
        : props.container.compose_project,
    )
  }
  return parts.join(' · ')
})

const actions = computed(() => {
  const list = isRunning.value
    ? ['restart', 'stop', 'pause']
    : isPaused.value
      ? ['unpause', 'restart', 'stop']
      : ['start', 'remove']
  return list
})

const ACTION_LABEL: Record<string, string> = {
  start: '启动',
  stop: '停止',
  restart: '重启',
  pause: '暂停',
  unpause: '继续',
  remove: '删除',
}
</script>

<template>
  <article class="container card" :class="{ 'container--busy': busy }">
    <div class="container__head">
      <span class="dot" :style="{ background: color }" />
      <div class="container__title">
        <span class="container__name truncate">{{ container.name }}</span>
        <span class="container__sub truncate dim">{{ subtitle }}</span>
      </div>
      <span class="badge" :style="{ color, background: 'transparent' }">
        {{ stateLabel(container.state) }}
      </span>
    </div>

    <div class="container__meta">
      <span class="mono dim" :title="container.id">{{ container.short_id }}</span>
      <span class="dim">·</span>
      <span class="dim">{{ created }}</span>
      <span v-if="container.ports.length" class="container__ports">
        <span v-for="port in container.ports" :key="port" class="badge mono">{{ port }}</span>
      </span>
    </div>

    <div class="container__actions">
      <button
        v-for="action in actions"
        :key="action"
        class="btn btn--sm"
        :class="action === 'remove' || action === 'stop' ? 'btn--danger' : ''"
        :disabled="busy"
        @click="emit('action', action)"
      >
        {{ ACTION_LABEL[action] ?? action }}
      </button>
      <button class="btn btn--sm btn--ghost" :disabled="busy" @click="emit('logs', container)">
        日志
      </button>
      <button
        v-for="command in commands ?? []"
        :key="command.id"
        class="btn btn--sm btn--ghost"
        :class="{ 'btn--danger': command.danger }"
        :disabled="busy"
        :title="command.description || command.argv.join(' ')"
        @click="emit('command', command)"
      >
        {{ command.name }}
      </button>
    </div>
  </article>
</template>

<style scoped>
.container {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 13px 15px;
  transition: border-color 0.15s ease;
}

.container:hover {
  border-color: var(--border-strong);
}

.container--busy {
  opacity: 0.65;
  pointer-events: none;
}

.container__head {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
}

.container__title {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}

.container__name {
  font-size: 14px;
  font-weight: 500;
}

.container__sub {
  font-size: 11.5px;
}

.container__meta {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
  font-size: 11.5px;
}

.container__ports {
  display: inline-flex;
  gap: 5px;
  flex-wrap: wrap;
}

.container__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
</style>
