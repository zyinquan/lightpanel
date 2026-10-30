<script setup lang="ts">
import type { TagSummary } from '@/api/types'

const props = defineProps<{
  tags: TagSummary[]
  selected: string[]
  matchAll?: boolean
}>()

const emit = defineEmits<{
  toggle: [string]
  'update:matchAll': [boolean]
  clear: []
}>()

const isSelected = (name: string) => props.selected.includes(name)
</script>

<template>
  <div class="tagfilter">
    <div class="tagfilter__row">
      <button class="chip" :class="{ 'chip--active': !selected.length }" @click="emit('clear')">
        全部
      </button>
      <button
        v-for="tag in tags"
        :key="tag.name"
        class="chip"
        :class="{ 'chip--active': isSelected(tag.name) }"
        @click="emit('toggle', tag.name)"
      >
        {{ tag.name }}
        <span class="tagfilter__count">{{ tag.count }}</span>
      </button>
    </div>
    <label v-if="selected.length > 1" class="tagfilter__match">
      <input
        type="checkbox"
        :checked="matchAll"
        @change="emit('update:matchAll', ($event.target as HTMLInputElement).checked)"
      />
      <span>同时满足所有标签</span>
    </label>
  </div>
</template>

<style scoped>
.tagfilter {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tagfilter__row {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}

.tagfilter__count {
  font-size: 11px;
  color: var(--text-dim);
}

.chip--active .tagfilter__count {
  color: inherit;
  opacity: 0.75;
}

.tagfilter__match {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-muted);
  cursor: pointer;
}
</style>
