<script setup lang="ts">
import { computed } from 'vue'
import type { SoftwareEntry } from '@/api/types'
import { colorFromString, initials, normalizeUrl } from '@/utils/format'
import { pushToast } from '@/composables/useToast'

const props = defineProps<{
  entry: SoftwareEntry
  activeTags?: string[]
}>()

const emit = defineEmits<{ tag: [string]; edit: [SoftwareEntry]; remove: [SoftwareEntry] }>()

const accent = computed(() => props.entry.color || colorFromString(props.entry.name))
/** 图标字符优先，留空才回落到名称首字母。 */
const mark = computed(() => props.entry.icon?.trim() || initials(props.entry.name))
const href = computed(() => normalizeUrl(props.entry.url))
const isActive = (tag: string) => props.activeTags?.includes(tag) ?? false

/**
 * 自己接管开窗，而不是只依赖 `target="_blank"`：
 * 面板跑在沙箱化内嵌预览里时，新窗口会被静默丢弃，看上去就是"点了没反应"。
 */
async function openEntry(event: MouseEvent) {
  const url = href.value
  if (!url) return
  // 带修饰键或非左键时交还给浏览器原生行为（新窗口/新标签/下载）。
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return
  event.preventDefault()
  const win = window.open(url, '_blank')
  if (win) {
    win.opener = null
    return
  }
  // 弹窗被拦截：至少把地址交到用户手里。
  const copied = await copyText(url)
  pushToast(
    copied ? `新窗口被拦截，链接已复制：${url}` : `新窗口被拦截，请手动打开：${url}`,
    'warning',
  )
}

async function copyText(text: string): Promise<boolean> {
  try {
    if (!navigator.clipboard?.writeText) return false
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}
</script>

<template>
  <article class="software card" :class="{ 'software--static': !href }">
    <a
      class="software__body"
      :href="href || undefined"
      :target="href ? '_blank' : undefined"
      rel="noreferrer noopener"
      :title="href || entry.name"
      @click="openEntry"
    >
      <span class="software__icon" :style="{ background: accent }">{{ mark }}</span>
      <span class="software__main">
        <span class="software__name truncate">{{ entry.name }}</span>
        <span v-if="entry.description" class="software__desc truncate">{{ entry.description }}</span>
        <span v-else-if="entry.category" class="software__desc truncate">{{ entry.category }}</span>
      </span>
    </a>

    <div class="software__tags">
      <button
        v-for="tag in entry.tags"
        :key="tag"
        class="chip chip--tag"
        :class="{ 'chip--active': isActive(tag) }"
        @click="emit('tag', tag)"
      >
        {{ tag }}
      </button>
    </div>

    <div class="software__actions">
      <button class="btn btn--ghost btn--sm" title="编辑" @click="emit('edit', entry)">编辑</button>
      <button class="btn btn--ghost btn--sm" title="删除" @click="emit('remove', entry)">
        删除
      </button>
    </div>
  </article>
</template>

<style scoped>
.software {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
  transition: border-color 0.15s ease, transform 0.15s ease;
}

.software:hover {
  border-color: var(--border-strong);
  transform: translateY(-1px);
}

.software__body {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

/* 整卡命中区：透明覆盖层把卡片的空白区域也变成链接，避免"只有标题行可点"。 */
.software__body::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
}

.software--static .software__body::after {
  content: none;
}

.software__icon {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  flex: none;
  border-radius: 10px;
  color: #fff;
  font-weight: 600;
  font-size: 15px;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.25);
}

.software__main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.software__name {
  font-size: 14px;
  font-weight: 500;
}

.software__desc {
  font-size: 12px;
  color: var(--text-dim);
}

/* 标签与操作按钮浮在整卡命中区之上，点击不会被链接吞掉。 */
.software__tags,
.software__actions {
  position: relative;
  z-index: 1;
}

.software__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.chip--tag {
  cursor: pointer;
}
.chip--tag:hover {
  border-color: var(--border-strong);
  color: var(--text);
}

.software__actions {
  display: flex;
  gap: 4px;
  margin-top: auto;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.software:hover .software__actions {
  opacity: 1;
}
</style>
