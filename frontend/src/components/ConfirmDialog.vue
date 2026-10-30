<script setup lang="ts">
import { ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    open: boolean
    title?: string
    message?: string
    confirmText?: string
    cancelText?: string
    danger?: boolean
    /** 要求手动输入该文本才能确认，用于高风险操作。 */
    expectText?: string
  }>(),
  {
    title: '请确认',
    message: '',
    confirmText: '确认',
    cancelText: '取消',
    danger: false,
    expectText: '',
  },
)

const emit = defineEmits<{ confirm: []; cancel: [] }>()

const typed = ref('')

watch(
  () => props.open,
  (open) => {
    if (open) typed.value = ''
  },
)

const canConfirm = () => !props.expectText || typed.value.trim() === props.expectText

function confirm() {
  if (!canConfirm()) return
  emit('confirm')
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') emit('cancel')
}
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="open" class="mask" @click.self="emit('cancel')" @keydown="onKeydown">
        <div class="dialog card" role="dialog" aria-modal="true">
          <h3 class="dialog__title">{{ title }}</h3>
          <p v-if="message" class="dialog__message">{{ message }}</p>
          <input
            v-if="expectText"
            v-model="typed"
            class="dialog__input"
            :placeholder="`请输入 ${expectText} 以确认`"
            autofocus
          />
          <div class="dialog__actions">
            <button class="btn" @click="emit('cancel')">{{ cancelText }}</button>
            <button
              class="btn"
              :class="danger ? 'btn--danger' : 'btn--primary'"
              :disabled="!canConfirm()"
              @click="confirm"
            >
              {{ confirmText }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.mask {
  position: fixed;
  inset: 0;
  z-index: 90;
  display: grid;
  place-items: center;
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(2px);
}

.dialog {
  width: min(440px, 92vw);
  padding: 20px;
  box-shadow: var(--shadow);
}

.dialog__title {
  font-size: 16px;
}

.dialog__message {
  margin: 10px 0 0;
  color: var(--text-muted);
  white-space: pre-wrap;
}

.dialog__input {
  margin-top: 12px;
  width: 100%;
  padding: 8px 10px;
  background: var(--bg);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  color: var(--text);
}

.dialog__input:focus {
  outline: none;
  border-color: var(--accent);
}

.dialog__actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 18px;
}
</style>
