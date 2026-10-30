<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppShell from '@/components/AppShell.vue'
import ToastHost from '@/components/ToastHost.vue'
import { api, storeToken } from '@/api/client'
import { usePolling } from '@/composables/usePolling'
import { errorMessage, pushToast } from '@/composables/useToast'
import type { AuthStatus } from '@/api/types'

const POLL_MS = 3000

const auth = ref<AuthStatus>({ enabled: false, authenticated: false })
const tokenInput = ref('')
const authLoading = ref(false)

const system = usePolling(() => api.system(), { interval: POLL_MS })
const docker = usePolling(() => api.dockerStatus(), { interval: POLL_MS * 2 })

const connectError = computed(() => {
  const err = system.error.value
  return err ? errorMessage(err) : null
})

async function loadAuth() {
  try {
    auth.value = await api.authStatus()
  } catch {
    auth.value = { enabled: false, authenticated: false }
  }
}

async function login() {
  authLoading.value = true
  try {
    storeToken(tokenInput.value.trim())
    auth.value = await api.login(tokenInput.value.trim())
    tokenInput.value = ''
    pushToast('已通过鉴权', 'success')
    await Promise.all([system.refresh(), docker.refresh()])
  } catch (error) {
    storeToken('')
    pushToast(errorMessage(error), 'error')
  } finally {
    authLoading.value = false
  }
}

onMounted(loadAuth)
</script>

<template>
  <div v-if="auth.enabled && !auth.authenticated" class="login">
    <form class="login__panel card" @submit.prevent="login">
      <div class="brand-lg">
        <span class="brand-lg__mark">LP</span>
        <h1>LightPanel</h1>
      </div>
      <p class="muted">该面板启用了访问令牌保护，请输入 API Token 后继续。</p>
      <input
        v-model="tokenInput"
        class="input"
        type="password"
        placeholder="X-LightPanel-Token"
        autofocus
      />
      <button class="btn btn--primary" type="submit" :disabled="authLoading || !tokenInput">
        {{ authLoading ? '校验中…' : '进入面板' }}
      </button>
    </form>
  </div>

  <AppShell v-else :system="system.data.value" :docker="docker.data.value" :error="connectError">
    <template #actions>
      <button class="btn btn--sm" :disabled="system.loading.value" @click="system.refresh()">
        {{ system.loading.value ? '刷新中…' : '刷新' }}
      </button>
    </template>
  </AppShell>

  <ToastHost />
</template>

<style scoped>
.login {
  display: grid;
  place-items: center;
  height: 100%;
}

.login__panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
  width: min(360px, 92vw);
  padding: 26px;
}

.brand-lg {
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand-lg h1 {
  font-size: 19px;
}

.brand-lg__mark {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: 9px;
  background: linear-gradient(135deg, var(--accent), var(--purple));
  color: #fff;
  font-weight: 700;
}

.login__panel p {
  margin: 0;
  font-size: 13px;
}
</style>
