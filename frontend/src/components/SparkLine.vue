<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    values: number[]
    width?: number
    height?: number
    /** 0-100 量纲；传 max 则按比例缩放。 */
    max?: number
    color?: string
    fill?: boolean
  }>(),
  { width: 160, height: 40, max: 100, color: 'var(--accent)', fill: true },
)

const points = computed(() => {
  const values = props.values.length ? props.values : [0]
  const max = props.max || 100
  const step = values.length > 1 ? props.width / (values.length - 1) : props.width
  return values.map((value, index) => {
    const x = index * step
    const clamped = Math.min(Math.max(value, 0), max)
    const y = props.height - (clamped / max) * (props.height - 4) - 2
    return [Number(x.toFixed(2)), Number(y.toFixed(2))] as const
  })
})

const line = computed(() => points.value.map(([x, y]) => `${x},${y}`).join(' '))

const area = computed(() => {
  if (!props.fill) return ''
  const first = points.value[0]
  const last = points.value[points.value.length - 1]
  return `M ${first[0]},${props.height} L ${line.value.replaceAll(' ', ' L ')} L ${last[0]},${props.height} Z`
})
</script>

<template>
  <svg
    class="sparkline"
    :viewBox="`0 0 ${width} ${height}`"
    :width="width"
    :height="height"
    preserveAspectRatio="none"
    aria-hidden="true"
  >
    <path v-if="fill" :d="area" :fill="color" opacity="0.15" />
    <polyline
      :points="line"
      fill="none"
      :stroke="color"
      stroke-width="1.6"
      stroke-linejoin="round"
      stroke-linecap="round"
    />
  </svg>
</template>

<style scoped>
.sparkline {
  display: block;
  overflow: visible;
}
</style>
