<script setup lang="ts">
import { useToast } from '@/composables/useToast'

const { toasts, dismiss } = useToast()
</script>

<template>
  <div class="toast-host" role="status" aria-live="polite">
    <TransitionGroup name="toast">
      <div
        v-for="toast in toasts"
        :key="toast.id"
        class="toast"
        :class="`toast--${toast.kind}`"
        @click="dismiss(toast.id)"
      >
        <span class="toast__dot" />
        <span class="toast__text">{{ toast.message }}</span>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toast-host {
  position: fixed;
  right: 20px;
  bottom: 20px;
  z-index: 100;
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 380px;
}

.toast {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 14px;
  background: var(--bg-elevated);
  border: 1px solid var(--border-strong);
  border-left-width: 3px;
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow);
  cursor: pointer;
}

.toast--success {
  border-left-color: var(--success);
}
.toast--error {
  border-left-color: var(--danger);
}
.toast--warning {
  border-left-color: var(--warning);
}
.toast--info {
  border-left-color: var(--accent);
}

.toast__dot {
  margin-top: 6px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  flex: none;
}

.toast--success .toast__dot {
  background: var(--success);
}
.toast--error .toast__dot {
  background: var(--danger);
}
.toast--warning .toast__dot {
  background: var(--warning);
}
.toast--info .toast__dot {
  background: var(--accent);
}

.toast__text {
  flex: 1;
  word-break: break-word;
}

.toast-enter-active,
.toast-leave-active {
  transition: all 0.2s ease;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateX(16px);
}
</style>
