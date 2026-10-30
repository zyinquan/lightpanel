<script setup lang="ts">
defineProps<{
  title: string
  value: string
  hint?: string
  accent?: string
}>()
</script>

<template>
  <div class="stat card">
    <div class="stat__title">{{ title }}</div>
    <div class="stat__value mono" :style="accent ? { color: accent } : undefined">{{ value }}</div>
    <div v-if="hint || $slots.default" class="stat__hint">
      <slot>{{ hint }}</slot>
    </div>
  </div>
</template>

<style scoped>
.stat {
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.stat__title {
  font-size: 12px;
  color: var(--text-muted);
}

.stat__value {
  font-size: 22px;
  font-weight: 600;
  letter-spacing: -0.02em;
  line-height: 1.2;
  overflow: hidden;
  text-overflow: ellipsis;
}

.stat__hint {
  font-size: 12px;
  color: var(--text-dim);
  min-height: 18px;
}
</style>
