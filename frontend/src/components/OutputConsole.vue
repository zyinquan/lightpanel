<script setup lang="ts">
import { computed } from 'vue'
import type { CommandResult } from '@/api/types'

const props = withDefaults(
  defineProps<{
    result: CommandResult | null
    title?: string
    collapsible?: boolean
  }>(),
  { title: '执行输出', collapsible: false },
)

const open = defineModel<boolean>('open', { default: true })

const body = computed(() => {
  if (!props.result) return ''
  const stdout = props.result.stdout ?? ''
  const stderr = props.result.stderr ?? ''
  if (stdout && stderr) return `${stdout}\n--- stderr ---\n${stderr}`
  return stdout || stderr || '(无输出)'
})

const argvText = computed(() => props.result?.argv.join(' ') ?? '')
</script>

<template>
  <div v-if="result" class="console">
    <div class="console__head">
      <span class="dot" :style="{ background: result.ok ? 'var(--success)' : 'var(--danger)' }" />
      <span class="console__title">{{ title }}</span>
      <span class="console__exit mono">exit {{ result.exit_code }}</span>
      <span class="console__ms mono">{{ result.duration_ms }} ms</span>
      <button v-if="collapsible" class="btn btn--ghost btn--sm" @click="open = !open">
        {{ open ? '收起' : '展开' }}
      </button>
    </div>
    <div v-show="open" class="console__body mono">{{ body }}</div>
    <div v-show="open" class="console__argv mono dim">$ {{ argvText }}</div>
  </div>
</template>

<style scoped>
.console {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  overflow: hidden;
  background: #0b1017;
}

.console__head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  background: var(--bg-elevated);
  border-bottom: 1px solid var(--border);
  font-size: 12px;
}

.console__title {
  font-weight: 500;
}

.console__exit,
.console__ms {
  font-size: 11px;
  color: var(--text-dim);
}

.console__exit {
  margin-left: auto;
}

.console__body {
  margin: 0;
  padding: 10px 12px;
  max-height: 280px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 12px;
  line-height: 1.5;
  color: #c9d4e0;
}

.console__argv {
  padding: 6px 12px;
  border-top: 1px solid var(--border);
  font-size: 11px;
}
</style>
