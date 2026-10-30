<script setup lang="ts">
import { computed } from 'vue'
import type { SoftwareEntry } from '@/api/types'
import { colorFromString, initials } from '@/utils/format'

const props = defineProps<{
  entry: SoftwareEntry
  activeTags?: string[]
}>()

const emit = defineEmits<{ tag: [string]; edit: [SoftwareEntry]; remove: [SoftwareEntry] }>()

const accent = computed(() => props.entry.color || colorFromString(props.entry.name))
const mark = computed(() => initials(props.entry.name))
const href = computed(() => props.entry.url || '')
const isActive = (tag: string) => props.activeTags?.includes(tag) ?? false
</script>

<template>
  <article class="software card">
    <a
      class="software__body"
      :href="href || undefined"
      :target="href ? '_blank' : undefined"
      rel="noreferrer noopener"
      :class="{ 'software__body--static': !href }"
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

.software__body--static {
  cursor: default;
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
