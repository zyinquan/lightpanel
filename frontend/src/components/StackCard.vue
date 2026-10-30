<script setup lang="ts">
import { computed } from 'vue'
import type { CommandDefinition, StackInfo } from '@/api/types'
import { stateColor, stateLabel } from '@/utils/format'

const props = defineProps<{
  stack: StackInfo
  commands?: CommandDefinition[]
  busy?: boolean
  expanded?: boolean
}>()

const emit = defineEmits<{
  action: [string]
  command: [CommandDefinition]
  toggle: []
}>()

const color = computed(() => stateColor(props.stack.status))
const ratio = computed(() =>
  props.stack.total ? Math.round((props.stack.running / props.stack.total) * 100) : 0,
)

const ACTIONS: Array<{ id: string; label: string; danger?: boolean }> = [
  { id: 'up', label: '启动' },
  { id: 'down', label: '停止' },
  { id: 'restart', label: '重启' },
  { id: 'pull', label: '拉取' },
  { id: 'build', label: '构建' },
]
</script>

<template>
  <article class="stack card" :class="{ 'stack--busy': busy }">
    <header class="stack__head">
      <button class="stack__expand" :aria-expanded="expanded" @click="emit('toggle')">
        {{ expanded ? '▾' : '▸' }}
      </button>
      <div class="stack__title">
        <span class="stack__name truncate">{{ stack.name }}</span>
        <span class="stack__path truncate dim">
          {{ stack.config_files || stack.working_dir || '—' }}
        </span>
      </div>
      <span class="badge" :style="{ color }">
        {{ stateLabel(stack.status) }}
        <span class="dim">{{ stack.running }}/{{ stack.total }}</span>
      </span>
    </header>

    <div class="stack__bar">
      <div class="stack__bar-fill" :style="{ width: `${ratio}%`, background: color }" />
    </div>

    <div class="stack__actions">
      <button
        v-for="action in ACTIONS"
        :key="action.id"
        class="btn btn--sm"
        :class="action.danger ? 'btn--danger' : ''"
        :disabled="busy"
        @click="emit('action', action.id)"
      >
        {{ action.label }}
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

    <div v-if="expanded && stack.containers.length" class="stack__containers">
      <div v-for="c in stack.containers" :key="c.id" class="stack__container">
        <span class="dot" :style="{ background: stateColor(c.state) }" />
        <span class="truncate">{{ c.name }}</span>
        <span class="dim truncate">{{ c.image }}</span>
        <span class="dim">{{ stateLabel(c.state) }}</span>
      </div>
    </div>
    <p v-else-if="expanded" class="stack__empty dim">该栈当前没有容器</p>
  </article>
</template>

<style scoped>
.stack {
  display: flex;
  flex-direction: column;
  gap: 9px;
  padding: 13px 15px;
  transition: border-color 0.15s ease;
}

.stack:hover {
  border-color: var(--border-strong);
}

.stack--busy {
  opacity: 0.65;
  pointer-events: none;
}

.stack__head {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.stack__expand {
  width: 20px;
  height: 20px;
  display: grid;
  place-items: center;
  background: transparent;
  border: none;
  color: var(--text-muted);
  font-size: 11px;
}

.stack__title {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}

.stack__name {
  font-size: 14px;
  font-weight: 500;
}

.stack__path {
  font-size: 11.5px;
  font-family: var(--mono);
}

.stack__bar {
  height: 4px;
  background: var(--bg-hover);
  border-radius: 999px;
  overflow: hidden;
}

.stack__bar-fill {
  height: 100%;
  border-radius: 999px;
  transition: width 0.3s ease;
}

.stack__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.stack__containers {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding-top: 8px;
  border-top: 1px solid var(--border);
}

.stack__container {
  display: grid;
  grid-template-columns: 10px minmax(0, 1.2fr) minmax(0, 1.6fr) 70px;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.stack__empty {
  margin: 0;
  padding-top: 6px;
  font-size: 12px;
}
</style>
