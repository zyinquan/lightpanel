<script setup lang="ts">
import { computed } from 'vue'
import { api } from '@/api/client'
import { usePolling } from '@/composables/usePolling'
import StatCard from '@/components/StatCard.vue'
import SparkLine from '@/components/SparkLine.vue'
import UsageBar from '@/components/UsageBar.vue'
import EmptyState from '@/components/EmptyState.vue'
import {
  formatBytes,
  formatDuration,
  formatPercent,
  stateColor,
  stateLabel,
  usageColor,
} from '@/utils/format'

const system = usePolling(() => api.system(), { interval: 3000 })
const history = usePolling(() => api.systemHistory(), { interval: 5000 })
const containers = usePolling(() => api.containers(), { interval: 5000 })
const stacks = usePolling(() => api.stacks(), { interval: 8000 })

const snap = computed(() => system.data.value)
const samples = computed(() => history.data.value ?? [])

const cpuSeries = computed(() => samples.value.map((s) => s.cpu_percent))
const memorySeries = computed(() => samples.value.map((s) => s.memory_percent))

const runningCount = computed(
  () => (containers.data.value ?? []).filter((c) => c.state === 'running').length,
)
const stackSummary = computed(() => {
  const list = stacks.data.value ?? []
  return { total: list.length, running: list.filter((s) => s.running > 0).length }
})

const network = computed(() => snap.value?.network ?? null)
const rootDisk = computed(() => {
  const disks = snap.value?.disks ?? []
  if (!disks.length) return null
  return [...disks].sort((a, b) => b.total - a.total)[0]
})

const load = computed(() => snap.value?.cpu.load_average ?? null)

/** 指标口径：看一眼就知道这些数字是宿主机的，还是面板容器的。 */
const scopeTitle = computed(() => (snap.value?.scope === 'container' ? '容器内指标' : '宿主机指标'))
const scopeDetail = computed(() => {
  const current = snap.value
  if (!current) return ''
  if (current.scope === 'container') {
    return current.hint ?? '面板运行在容器内：网络与磁盘只覆盖本容器，CPU / 内存取所在内核。'
  }
  const source = current.source === 'agent' ? '宿主机代理' : '本机 psutil'
  return `来自 ${current.host.hostname} · 采集自${source}`
})
</script>

<template>
  <section>
    <div v-if="snap" class="scope" :class="`scope--${snap.scope}`" data-test="scope">
      <span class="scope__tag">
        <span
          class="dot"
          :style="{ background: snap.scope === 'host' ? 'var(--success)' : 'var(--warning)' }"
        />
        {{ scopeTitle }}
      </span>
      <span class="scope__text">{{ scopeDetail }}</span>
    </div>

    <div class="grid-stats">
      <StatCard
        title="CPU"
        :value="formatPercent(snap?.cpu.percent ?? 0)"
        :accent="usageColor(snap?.cpu.percent ?? 0)"
      >
        <SparkLine :values="cpuSeries" :width="150" :height="28" :color="usageColor(snap?.cpu.percent ?? 0)" />
      </StatCard>

      <StatCard
        title="内存"
        :value="formatPercent(snap?.memory.percent ?? 0)"
        :accent="usageColor(snap?.memory.percent ?? 0)"
      >
        <SparkLine :values="memorySeries" :width="150" :height="28" color="var(--purple)" />
      </StatCard>

      <StatCard title="负载" :value="load ? load.map((v) => v.toFixed(2)).join(' / ') : '—'">
        {{ snap?.cpu.logical_count ?? '—' }} 逻辑核心
      </StatCard>

      <StatCard title="运行时间" :value="snap ? formatDuration(snap.host.uptime_seconds) : '—'">
        {{ snap?.host.os_name ?? '' }}
      </StatCard>

      <StatCard title="容器" :value="`${runningCount} / ${containers.data.value?.length ?? 0}`">
        运行中 / 总数
      </StatCard>

      <StatCard title="编排栈" :value="`${stackSummary.running} / ${stackSummary.total}`">
        活跃 / 总数
      </StatCard>
    </div>

    <div class="grid-detail">
      <div class="card panel">
        <h2 class="section-title">资源使用</h2>
        <div class="panel__body">
          <UsageBar
            :percent="snap?.cpu.percent ?? 0"
            label="CPU"
            :detail="`${snap?.cpu.logical_count ?? 0} 核`"
          />
          <UsageBar
            :percent="snap?.memory.percent ?? 0"
            label="内存"
            :detail="snap ? `${snap.memory.used_human} / ${snap.memory.total_human}` : ''"
          />
          <UsageBar
            v-if="snap && snap.memory.swap_total > 0"
            :percent="snap.memory.swap_percent"
            label="Swap"
            :detail="`${formatBytes(snap.memory.swap_used)} / ${formatBytes(snap.memory.swap_total)}`"
          />
          <UsageBar
            v-if="rootDisk"
            :percent="rootDisk.percent"
            :label="`磁盘 ${rootDisk.mountpoint}`"
            :detail="`${rootDisk.used_human} / ${rootDisk.total_human}`"
          />
        </div>
      </div>

      <div class="card panel">
        <h2 class="section-title">主机信息</h2>
        <dl class="kv">
          <div><dt>主机名</dt><dd class="mono">{{ snap?.host.hostname ?? '—' }}</dd></div>
          <div><dt>系统</dt><dd>{{ snap?.host.os_name ?? '—' }} {{ snap?.host.os_version ?? '' }}</dd></div>
          <div><dt>架构</dt><dd class="mono">{{ snap?.host.arch ?? '—' }}</dd></div>
          <div><dt>内存</dt><dd class="mono">{{ snap?.memory.total_human ?? '—' }}</dd></div>
          <div>
            <dt>网络</dt>
            <dd class="mono">
              ↓ {{ formatBytes(network?.bytes_recv ?? 0) }} · ↑
              {{ formatBytes(network?.bytes_sent ?? 0) }}
            </dd>
          </div>
          <div><dt>采样时间</dt><dd class="mono">{{ snap?.collected_at?.slice(11, 19) ?? '—' }}</dd></div>
        </dl>
      </div>

      <div class="card panel panel--wide">
        <h2 class="section-title">容器状态</h2>
        <div v-if="(containers.data.value?.length ?? 0) === 0" class="panel__body">
          <EmptyState title="暂无容器" description="未检测到 Docker 容器，或引擎不可用。" />
        </div>
        <div v-else class="ctable">
          <div v-for="c in containers.data.value ?? []" :key="c.id" class="ctable__row">
            <span class="dot" :style="{ background: stateColor(c.state) }" />
            <span class="ctable__name truncate">{{ c.name }}</span>
            <span class="ctable__image truncate dim">{{ c.image }}</span>
            <span class="ctable__state" :style="{ color: stateColor(c.state) }">
              {{ stateLabel(c.state) }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.scope {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 12px;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg-soft, rgba(255, 255, 255, 0.02));
  font-size: 12.5px;
}

.scope__tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: none;
  font-weight: 600;
}

.scope--container {
  border-color: rgba(210, 153, 34, 0.45);
  background: rgba(210, 153, 34, 0.08);
}

.scope--container .scope__tag {
  color: var(--warning);
}

.scope__text {
  color: var(--text-dim);
  line-height: 1.5;
}

.grid-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}

.grid-detail {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 12px;
}

.panel {
  padding: 16px;
}

.panel--wide {
  grid-column: 1 / -1;
}

.panel__body {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.kv {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  font-size: 13px;
}

.kv > div {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.kv dt {
  width: 74px;
  flex: none;
  color: var(--text-muted);
  font-size: 12.5px;
}

.kv dd {
  margin: 0;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ctable {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 6px 18px;
}

.ctable__row {
  display: grid;
  grid-template-columns: 10px minmax(0, 1fr) minmax(0, 1.4fr) 60px;
  align-items: center;
  gap: 9px;
  padding: 5px 0;
  font-size: 12.5px;
  border-bottom: 1px solid rgba(35, 44, 56, 0.5);
}

.ctable__state {
  text-align: right;
  font-size: 11.5px;
}
</style>
