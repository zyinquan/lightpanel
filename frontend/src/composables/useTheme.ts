/** 黑/白主题切换：持久化到 localStorage，默认深色。 */

import { ref } from 'vue'

export type Theme = 'dark' | 'light'

const STORAGE_KEY = 'lightpanel.theme'

function readStored(): Theme {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'light' ? 'light' : 'dark'
  } catch {
    return 'dark'
  }
}

const theme = ref<Theme>('dark')

/** 应用到 <html data-theme>；模块加载时调用一次。 */
function apply(value: Theme) {
  theme.value = value
  document.documentElement.dataset.theme = value
}

apply(readStored())

export function useTheme() {
  function set(value: Theme) {
    apply(value)
    try {
      localStorage.setItem(STORAGE_KEY, value)
    } catch {
      /* 隐私模式等场景写不进去就算了，本次会话仍然生效 */
    }
  }

  function toggle() {
    set(theme.value === 'dark' ? 'light' : 'dark')
  }

  return { theme, set, toggle }
}
