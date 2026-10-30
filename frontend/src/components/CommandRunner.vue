<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api, ApiError } from '@/api/client'
import type { CommandDefinition, CommandResult } from '@/api/types'
import OutputConsole from './OutputConsole.vue'
import { pushToast } from '@/composables/useToast'

const props = defineProps<{
  open: boolean
  command: CommandDefinition | null
  targetId?: string
  targetLabel?: string
}>()

const emit = defineEmits<{ close: []; executed: [CommandResult] }>()

const extraArgs = ref('')
const timeout = ref<number | null>(null)
const result = ref<CommandResult | null>(null)
const running = ref(false)

watch(
  () => [props.open, props.command?.id] as const,
  () => {
    extraArgs.value = ''
    timeout.value = null
    result.value = null
    running.value = false
  },
)

const parsedExtra = computed(() =>
  extraArgs.value
    .split(/\s+/)
    .map((s) => s.trim())
    .filter(Boolean),
)

const preview = computed(() => {
  if (!props.command) return ''
  return [...props.command.argv, ...parsedExtra.value].join(' ')
})

const needsConfirm = computed(() => props.command?.confirm ?? false)

async function run() {
  if (!props.command) return
  running.value = true
  result.value = null
  try {
    const output = await api.runCommand(props.command.id, {
      targetId: props.targetId,
      extraArgs: parsedExtra.value,
      timeout: timeout.value ?? undefined,
    })
    result.value = output
    emit('executed', output)
    if (output.ok) pushToast(`${props.command.name} 执行成功`, 'success')
    else pushToast(`${props.command.name} 退出码 ${output.exit_code}`, 'error')
  } catch (error) {
    const message = error instanceof ApiError ? error.message : String(error)
    pushToast(message, 'error')
    result.value = {
      ok: false,
      exit_code: -1,
      argv: props.command.argv,
      stdout: '',
      stderr: message,
      duration_ms: 0,
    }
  } finally {
    running.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="open && command" class="mask" @click.self="emit('close')">
        <div class="runner card" role="dialog" aria-modal="true">
          <header class="runner__head">
            <div>
              <h3 class="runner__title">{{ command.name }}</h3>
              <p class="runner__sub dim">
                {{ targetLabel ? `${targetLabel} · ` : '' }}{{ command.id }}
              </p>
            </div>
            <button class="btn btn--ghost btn--sm" @click="emit('close')">✕</button>
          </header>

          <p v-if="command.description" class="runner__desc">{{ command.description }}</p>

          <div class="runner__preview mono">$ {{ preview }}</div>

          <div class="runner__fields">
            <label class="field">
              <span class="field__label">附加参数（空格分隔）</span>
              <input v-model="extraArgs" class="input" placeholder="例如 --force -d" />
            </label>
            <label class="field runner__timeout">
              <span class="field__label">超时（秒）</span>
              <input
                v-model.number="timeout"
                class="input"
                type="number"
                min="1"
                :placeholder="String(command.timeout)"
              />
            </label>
          </div>

          <OutputConsole :result="result" title="执行结果" />

          <footer class="runner__foot">
            <span v-if="needsConfirm" class="runner__warn">该命令标记为需确认，请确认后执行</span>
            <span class="spacer" />
            <button class="btn" @click="emit('close')">关闭</button>
            <button
              class="btn"
              :class="command.danger ? 'btn--danger' : 'btn--primary'"
              :disabled="running"
              @click="run"
            >
              {{ running ? '执行中…' : '执行' }}
            </button>
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.mask {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: grid;
  place-items: center;
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(2px);
}

.runner {
  width: min(640px, 94vw);
  max-height: 88vh;
  overflow: auto;
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  box-shadow: var(--shadow);
}

.runner__head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.runner__title {
  font-size: 15px;
}

.runner__sub {
  margin: 2px 0 0;
  font-size: 11.5px;
  font-family: var(--mono);
}

.runner__desc {
  margin: 0;
  font-size: 13px;
  color: var(--text-muted);
}

.runner__preview {
  padding: 9px 11px;
  background: #0b1017;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 12px;
  word-break: break-all;
}

.runner__fields {
  display: flex;
  gap: 10px;
}

.runner__fields .field {
  flex: 1;
}

.runner__timeout {
  max-width: 120px;
}

.runner__foot {
  display: flex;
  align-items: center;
  gap: 10px;
}

.runner__warn {
  font-size: 12px;
  color: var(--warning);
}
</style>
