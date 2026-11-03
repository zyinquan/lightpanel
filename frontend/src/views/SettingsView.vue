<script setup lang="ts">
import { computed, ref } from 'vue'
import { api, storeToken } from '@/api/client'
import { errorMessage, pushToast } from '@/composables/useToast'
import { useTheme } from '@/composables/useTheme'

const { theme, set: setTheme } = useTheme()

const THEMES = [
  { value: 'dark' as const, label: '深色', swatch: '#0d1117' },
  { value: 'light' as const, label: '浅色', swatch: '#f4f6f9' },
]

// 是否启用了鉴权：status 在未鉴权时也回答 enabled
const authEnabled = ref<boolean | null>(null)
api.authStatus().then((s) => (authEnabled.value = s.enabled)).catch(() => (authEnabled.value = null))

const current = ref('')
const next = ref('')
const confirm = ref('')
const saving = ref(false)

const mismatch = computed(() => confirm.value !== '' && confirm.value !== next.value)
const canSubmit = computed(
  () => current.value && next.value.length >= 6 && !mismatch.value && !saving.value,
)

async function savePassword() {
  saving.value = true
  try {
    await api.changePassword(current.value, next.value)
    storeToken(next.value) // 旧令牌已作废，本地立刻换新，避免下一次请求 401
    pushToast('登录密码已更新', 'success')
    current.value = next.value = confirm.value = ''
  } catch (error) {
    pushToast(errorMessage(error), 'error')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="settings">
    <h2 class="settings__title">设置</h2>

    <section class="card block">
      <h3>外观</h3>
      <p class="muted hint">切换面板的深浅配色，选择会被记住。</p>
      <div class="theme-row">
        <button
          v-for="item in THEMES"
          :key="item.value"
          class="theme-option"
          :class="{ 'theme-option--active': theme === item.value }"
          type="button"
          @click="setTheme(item.value)"
        >
          <span class="theme-option__swatch" :style="{ background: item.swatch }" />
          <span>{{ item.label }}</span>
          <span v-if="theme === item.value" class="theme-option__check">✓</span>
        </button>
      </div>
    </section>

    <section class="card block">
      <h3>登录密码</h3>
      <template v-if="authEnabled === false">
        <p class="muted hint">
          当前面板未启用鉴权，无需登录密码。启用方式：配置文件中设置
          <code>security.enabled: true</code> 与 <code>security.api_token</code>，然后重启服务。
        </p>
      </template>
      <template v-else>
        <p class="muted hint">
          登录密码即 API Token，修改后立即生效并写入配置文件（重启不会丢失）。
          其他已登录的会话将失效，需要用新密码重新登录。
        </p>
        <form class="pwd" @submit.prevent="savePassword">
          <label class="pwd__field">
            <span class="muted">当前密码</span>
            <input v-model="current" class="input" type="password" autocomplete="current-password" />
          </label>
          <label class="pwd__field">
            <span class="muted">新密码（至少 6 位）</span>
            <input v-model="next" class="input" type="password" autocomplete="new-password" />
          </label>
          <label class="pwd__field">
            <span class="muted">确认新密码</span>
            <input v-model="confirm" class="input" type="password" autocomplete="new-password" />
            <span v-if="mismatch" class="pwd__error">两次输入不一致</span>
          </label>
          <button class="btn btn--primary pwd__save" type="submit" :disabled="!canSubmit">
            {{ saving ? '保存中…' : '保存新密码' }}
          </button>
        </form>
      </template>
    </section>
  </div>
</template>

<style scoped>
.settings {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 620px;
}

.settings__title {
  font-size: 18px;
}

.block {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 18px 20px;
}

.block h3 {
  font-size: 15px;
}

.hint {
  font-size: 13px;
  margin: 0;
}

.theme-row {
  display: flex;
  gap: 10px;
}

.theme-option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg-hover);
  color: var(--text);
}

.theme-option--active {
  border-color: var(--accent);
  background: var(--accent-soft);
}

.theme-option__swatch {
  width: 14px;
  height: 14px;
  border-radius: 4px;
  border: 1px solid var(--border-strong);
}

.theme-option__check {
  color: var(--accent);
}

.pwd {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-width: 380px;
}

.pwd__field {
  display: flex;
  flex-direction: column;
  gap: 5px;
  font-size: 13px;
}

.pwd__error {
  color: var(--danger);
  font-size: 12px;
}

.pwd__save {
  align-self: flex-start;
}
</style>
