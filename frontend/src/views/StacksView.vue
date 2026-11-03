<script setup lang="ts">
import { computed, ref } from 'vue'
import { api } from '@/api/client'
import type { CommandDefinition, ContainerUsage, StackInfo } from '@/api/types'
import { usePolling } from '@/composables/usePolling'
import { errorMessage, pushToast } from '@/composables/useToast'
import StackCard from '@/components/StackCard.vue'
import CommandRunner from '@/components/CommandRunner.vue'
import EmptyState from '@/components/EmptyState.vue'

const search = ref('')
const stacks = usePolling(() => api.stacks(), { interval: 8000 })
const commands = usePolling(() => api.commands('stack'), { interval: 30000 })
// 容器占用按 ID 索引，编排卡的整栈数字由各容器求和得来
const usage = usePolling(() => api.containerUsage(), { interval: 8000 })
const usageById = computed(() => {
  const map: Record<string, ContainerUsage> = {}
  for (const item of usage.data.value?.items ?? []) map[item.container_id] = item
  return map
})

const filtered = computed(() => {
  const list = stacks.data.value ?? []
  const keyword = search.value.trim().toLowerCase()
  if (!keyword) return list
  return list.filter((s) => s.name.toLowerCase().includes(keyword))
})

const customCommands = computed(() => (commands.data.value ?? []).filter((c) => !c.builtin))
const busy = ref<Record<string, boolean>>({})
const expanded = ref<Record<string, boolean>>({})

const runnerCommand = ref<CommandDefinition | null>(null)
const runnerTarget = ref('')
const runnerOpen = computed({
  get: () => runnerCommand.value !== null,
  set: (value: boolean) => {
    if (!value) runnerCommand.value = null
  },
})

function openCommand(command: CommandDefinition, stack: StackInfo) {
  runnerCommand.value = command
  runnerTarget.value = stack.name
}

async function act(stack: StackInfo, action: string) {
  busy.value = { ...busy.value, [stack.name]: true }
  try {
    await api.stackAction(stack.name, action as 'up')
    pushToast(`${stack.name} ${action} 完成`, 'success')
    await stacks.refresh()
  } catch (error) {
    pushToast(errorMessage(error), 'error')
  } finally {
    const next = { ...busy.value }
    delete next[stack.name]
    busy.value = next
  }
}
</script>

<template>
  <section>
    <header class="bar">
      <input v-model="search" class="input bar__search" placeholder="搜索编排栈…" />
      <span class="spacer" />
      <span class="dim">{{ filtered.length }} 个栈</span>
      <button class="btn" :disabled="stacks.loading.value" @click="stacks.refresh()">刷新</button>
    </header>

    <div v-if="stacks.error.value" class="banner" data-test="stacks-error">
      <span class="banner__tag">栈列表不可用</span>
      <span class="banner__text">{{ errorMessage(stacks.error.value) }}</span>
    </div>

    <div v-if="filtered.length" class="list">
      <StackCard
        v-for="stack in filtered"
        :key="stack.name"
        :stack="stack"
        :usage-by-id="usageById"
        :commands="customCommands"
        :busy="busy[stack.name]"
        :expanded="expanded[stack.name]"
        @action="act(stack, $event)"
        @command="openCommand($event, stack)"
        @toggle="expanded = { ...expanded, [stack.name]: !expanded[stack.name] }"
      />
    </div>
    <EmptyState
      v-else-if="!stacks.error.value"
      title="没有编排栈"
      description="把 docker-compose.yml 放进 compose.search_paths（或宿主机代理的 --stacks-root）下的目录即可被发现。"
    />

    <CommandRunner
      :open="runnerOpen"
      :command="runnerCommand"
      :target-id="runnerTarget"
      :target-label="runnerTarget"
      @close="runnerCommand = null"
      @executed="stacks.refresh()"
    />
  </section>
</template>

<style scoped>
.banner {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 12px;
  padding: 8px 12px;
  border: 1px solid rgba(248, 81, 73, 0.35);
  border-radius: var(--radius);
  background: rgba(248, 81, 73, 0.08);
  font-size: 12.5px;
}

.banner__tag {
  flex: none;
  font-weight: 600;
  color: var(--danger);
}

.banner__text {
  color: var(--text);
  word-break: break-word;
}

.bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}

.bar__search {
  width: min(280px, 60vw);
}

.list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 12px;
}
</style>
