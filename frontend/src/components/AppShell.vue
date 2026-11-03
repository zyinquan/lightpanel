<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import type { EngineStatus, SystemSnapshot } from '@/api/types'
import { formatDuration } from '@/utils/format'
import { useTheme } from '@/composables/useTheme'

const props = defineProps<{
  system: SystemSnapshot | null
  docker: EngineStatus | null
  error?: string | null
}>()

const route = useRoute()
const { theme, toggle: toggleTheme } = useTheme()

const NAV = [
  { to: '/', label: '概览', icon: '▤' },
  { to: '/catalog', label: '软件', icon: '◈' },
  { to: '/containers', label: '容器', icon: '▣' },
  { to: '/stacks', label: '编排', icon: '≡' },
  { to: '/commands', label: '命令', icon: '⌘' },
  { to: '/settings', label: '设置', icon: '⚙' },
]

const uptime = computed(() =>
  props.system ? formatDuration(props.system.host.uptime_seconds) : '—',
)
const engineLabel = computed(() => {
  if (!props.docker) return '检测中…'
  return props.docker.available ? `Docker ${props.docker.running}/${props.docker.total}` : 'Docker 不可用'
})
</script>

<template>
  <div class="shell">
    <aside class="shell__side">
      <div class="brand">
        <span class="brand__mark">LP</span>
        <span class="brand__name">LightPanel</span>
      </div>
      <nav class="nav">
        <RouterLink
          v-for="item in NAV"
          :key="item.to"
          :to="item.to"
          class="nav__item"
          :class="{ 'nav__item--active': route.path === item.to }"
        >
          <span class="nav__icon">{{ item.icon }}</span>
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>
      <div class="shell__side-foot">
        <div class="side-stat">
          <span class="dim">运行时间</span>
          <strong class="mono">{{ uptime }}</strong>
        </div>
        <div class="side-stat">
          <span class="dim">Docker</span>
          <strong>{{ engineLabel }}</strong>
        </div>
      </div>
    </aside>

    <main class="shell__main">
      <header class="topbar">
        <div class="topbar__meta">
          <span class="topbar__host">{{ system?.host.hostname ?? '未连接' }}</span>
          <span class="dim">{{ system?.host.os_name ?? '' }} {{ system?.host.arch ?? '' }}</span>
        </div>
        <span class="spacer" />
        <button
          class="btn btn--sm theme-toggle"
          :title="theme === 'dark' ? '切换到浅色' : '切换到深色'"
          @click="toggleTheme"
        >
          {{ theme === 'dark' ? '☀' : '☾' }}
        </button>
        <span v-if="error" class="badge" style="color: var(--danger)">{{ error }}</span>
        <span v-else class="badge">
          <span class="dot" style="background: var(--success)" />
          已连接
        </span>
        <slot name="actions" />
      </header>

      <div class="shell__content">
        <RouterView />
      </div>
    </main>
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  height: 100%;
  overflow: hidden;
}

.shell__side {
  display: flex;
  flex-direction: column;
  width: 200px;
  flex: none;
  padding: 16px 12px;
  background: var(--bg-elevated);
  border-right: 1px solid var(--border);
}

.brand {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 4px 6px 18px;
}

.brand__mark {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 8px;
  background: linear-gradient(135deg, var(--accent), var(--purple));
  color: #fff;
  font-weight: 700;
  font-size: 13px;
}

.brand__name {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: -0.01em;
}

.nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav__item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  font-size: 13.5px;
  transition: background 0.15s ease, color 0.15s ease;
}

.nav__item:hover {
  background: var(--bg-hover);
  color: var(--text);
}

.nav__item--active {
  background: var(--accent-soft);
  color: var(--nav-active-text);
}

.nav__icon {
  width: 16px;
  text-align: center;
  opacity: 0.85;
}

.shell__side-foot {
  margin-top: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 8px 0;
  border-top: 1px solid var(--border);
}

.side-stat {
  display: flex;
  flex-direction: column;
  font-size: 12px;
}

.side-stat strong {
  font-weight: 500;
  font-size: 12.5px;
}

.shell__main {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.topbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 22px;
  border-bottom: 1px solid var(--border);
  background: var(--topbar-bg);
}

.theme-toggle {
  width: 34px;
  text-align: center;
  font-size: 15px;
}

.topbar__meta {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.topbar__host {
  font-size: 15px;
  font-weight: 600;
}

.shell__content {
  flex: 1;
  overflow-y: auto;
  padding: 20px 22px 40px;
}

@media (max-width: 860px) {
  .shell__side {
    width: 64px;
    padding: 14px 8px;
  }
  .brand__name,
  .nav__item span:not(.nav__icon),
  .shell__side-foot {
    display: none;
  }
  .nav__item {
    justify-content: center;
  }
}
</style>
