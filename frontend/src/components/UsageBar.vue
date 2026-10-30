<script setup lang="ts">
import { computed } from 'vue'
import { usageColor } from '@/utils/format'

const props = withDefaults(
  defineProps<{
    percent: number
    height?: number
    label?: string
    detail?: string
    showPercent?: boolean
  }>(),
  { height: 6, label: '', detail: '', showPercent: true },
)

const clamped = computed(() => Math.min(Math.max(props.percent, 0), 100))
const color = computed(() => usageColor(clamped.value))
</script>

<template>
  <div class="usage">
    <div v-if="label || detail || showPercent" class="usage__head">
      <span v-if="label" class="usage__label">{{ label }}</span>
      <span v-if="detail" class="usage__detail dim">{{ detail }}</span>
      <span v-if="showPercent" class="usage__percent mono">{{ clamped.toFixed(1) }}%</span>
    </div>
    <div class="usage__track" :style="{ height: `${height}px` }">
      <div
        class="usage__fill"
        :style="{ width: `${clamped}%`, background: color }"
        role="progressbar"
        :aria-valuenow="Math.round(clamped)"
        aria-valuemin="0"
        aria-valuemax="100"
      />
    </div>
  </div>
</template>

<style scoped>
.usage {
  width: 100%;
}

.usage__head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 5px;
  font-size: 12px;
}

.usage__label {
  color: var(--text-muted);
}

.usage__detail {
  font-size: 11px;
}

.usage__percent {
  margin-left: auto;
  font-size: 12px;
  color: var(--text);
}

.usage__track {
  width: 100%;
  background: var(--bg-hover);
  border-radius: 999px;
  overflow: hidden;
}

.usage__fill {
  height: 100%;
  border-radius: 999px;
  transition: width 0.4s ease;
}
</style>
