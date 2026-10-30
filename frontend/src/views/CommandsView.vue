<script setup lang="ts">
import { computed, ref } from 'vue'
import { api } from '@/api/client'
import type { CommandDefinition, CommandResult, CommandTarget } from '@/api/types'
import { usePolling } from '@/composables/usePolling'
import { errorMessage, pushToast } from '@/composables/useToast'
import OutputConsole from '@/components/OutputConsole.vue'
import EmptyState from '@/components/EmptyState.vue'

const commands = usePolling(() => api.commands(), { interval: 30000 })

const TARGET_LABEL: Record<CommandTarget, string> = {
  container: '容器',
  stack: '编排栈',
  system: '系统',
}

const grouped = computed(() => {
  const map = new Map<CommandTarget, CommandDefinition[]>()
  for (const command of commands.data.value ?? []) {
    const list = map.get(command.target) ?? []
    list.push(command)
    map.set(command.target, list)
  }
  return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0]))
})

// ---- 定义命令的执行 --------------------------------------------------------
const targetId = ref('')
const activeCommand = ref<CommandDefinition | null>(null)
const defResult = ref<CommandResult | null>(null)
const defRunning = ref(false)

async function runDefinition(command: CommandDefinition) {
  activeCommand.value = command
  defRunning.value = true
  defResult.value = null
  try {
    defResult.value = await api.runCommand(command.id, {
      targetId: targetId.value || undefined,
    })
    if (!defResult.value.ok) pushToast(`退出码 ${defResult.value.exit_code}`, 'error')
  } catch (error) {
    pushToast(errorMessage(error), 'error')
  } finally {
    defRunning.value = false
  }
}

// ---- 临时命令 --------------------------------------------------------------
const adHoc = ref('docker ps --format "table {{.Names}}\t{{.Status}}"')
const adhocResult = ref<CommandResult | null>(null)
const adhocRunning = ref(false)

async function runAdHoc() {
  const argv = adHoc.value.trim().split(/\s+/).filter(Boolean)
  if (!argv.length) {
    pushToast('请输入命令', 'warning')
    return
  }
  adhocRunning.value = true
  adhocResult.value = null
  try {
    adhocResult.value = await api.runAdHoc({ argv })
    if (!adhocResult.value.ok) pushToast(`退出码 ${adhocResult.value.exit_code}`, 'error')
  } catch (error) {
    pushToast(errorMessage(error), 'error')
  } finally {
    adhocRunning.value = false
  }
}
</script>

<template>
  <section>
    <div class="card panel">
      <h2 class="section-title">临时命令</h2>
      <p class="panel__hint dim">
        仅允许配置中白名单内的可执行文件（默认 docker / docker-compose），且禁止 shell 解释器与危险参数。
      </p>
      <div class="adhoc">
        <input
          v-model="adHoc"
          class="input mono adhoc__input"
          placeholder="docker ps"
          @keydown.enter="runAdHoc"
        />
        <button class="btn btn--primary" :disabled="adhocRunning" @click="runAdHoc">
          {{ adhocRunning ? '执行中…' : '执行' }}
        </button>
      </div>
      <OutputConsole v-if="adhocResult" :result="adhocResult" title="临时命令结果" class="panel__out" />
    </div>

    <div class="card panel">
      <h2 class="section-title">已注册命令</h2>
      <div class="panel__hint row">
        <span class="dim">对容器 / 栈执行命令时填写目标标识：</span>
        <input v-model="targetId" class="input target" placeholder="容器名 或 栈名" />
      </div>

      <div v-if="grouped.length" class="groups">
        <div v-for="[target, list] in grouped" :key="target" class="group">
          <h3 class="group__title">{{ TARGET_LABEL[target] ?? target }}（{{ list.length }}）</h3>
          <div class="group__list">
            <div v-for="command in list" :key="command.id" class="cmd">
              <div class="cmd__main">
                <div class="cmd__head">
                  <span class="cmd__name">{{ command.name }}</span>
                  <span v-if="command.builtin" class="badge">内置</span>
                  <span v-if="command.danger" class="badge" style="color: var(--danger)">高危</span>
                  <span v-if="command.confirm" class="badge">需确认</span>
                </div>
                <div class="cmd__argv mono dim">{{ command.argv.join(' ') }}</div>
                <div v-if="command.description" class="cmd__desc dim">{{ command.description }}</div>
              </div>
              <button
                class="btn btn--sm"
                :class="command.danger ? 'btn--danger' : ''"
                :disabled="defRunning"
                @click="runDefinition(command)"
              >
                执行
              </button>
            </div>
          </div>
        </div>
      </div>
      <EmptyState v-else title="没有命令定义" description="在 data/commands.yaml 中添加自定义命令。" />

      <OutputConsole
        v-if="defResult"
        :result="defResult"
        :title="activeCommand?.name ?? '执行结果'"
        class="panel__out"
      />
    </div>
  </section>
</template>

<style scoped>
.panel {
  padding: 16px;
  margin-bottom: 12px;
}

.panel__hint {
  margin: 0 0 10px;
  font-size: 12.5px;
}

.panel__out {
  margin-top: 12px;
}

.adhoc {
  display: flex;
  gap: 10px;
}

.adhoc__input {
  flex: 1;
  font-size: 12.5px;
}

.target {
  width: 200px;
}

.groups {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
}

.group__title {
  margin-bottom: 8px;
  font-size: 13px;
  color: var(--text-muted);
}

.group__list {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.cmd {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 11px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-elevated);
}

.cmd__main {
  flex: 1;
  min-width: 0;
}

.cmd__head {
  display: flex;
  align-items: center;
  gap: 7px;
}

.cmd__name {
  font-size: 13.5px;
  font-weight: 500;
}

.cmd__argv {
  margin-top: 2px;
  font-size: 11.5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cmd__desc {
  font-size: 11.5px;
}
</style>
