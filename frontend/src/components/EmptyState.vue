<script setup lang="ts">
withDefaults(
  defineProps<{
    title?: string
    description?: string
    icon?: string
  }>(),
  { title: '暂无数据', description: '', icon: '📭' },
)
</script>

<template>
  <div class="empty">
    <div class="empty__icon">{{ icon }}</div>
    <div class="empty__title">{{ title }}</div>
    <p v-if="description" class="empty__desc">{{ description }}</p>
    <slot />
  </div>
</template>

<style scoped>
.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 40px 20px;
  text-align: center;
  color: var(--text-dim);
}

.empty__icon {
  font-size: 30px;
  opacity: 0.7;
}

.empty__title {
  font-size: 14px;
  color: var(--text-muted);
}

.empty__desc {
  margin: 0;
  max-width: 420px;
  font-size: 12.5px;
}
</style>
