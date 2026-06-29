import { ref, watchEffect } from 'vue'

const THEME_KEY = 'app-theme'
const isDark = ref(false)

export function useTheme() {
  // 初始化：读取 localStorage 或系统偏好
  const stored = localStorage.getItem(THEME_KEY)
  if (stored) {
    isDark.value = stored === 'dark'
  } else {
    isDark.value = window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
  }
  applyTheme()

  function applyTheme() {
    document.documentElement.dataset.theme = isDark.value ? 'dark' : 'light'
    localStorage.setItem(THEME_KEY, isDark.value ? 'dark' : 'light')
  }

  function toggle() {
    isDark.value = !isDark.value
    applyTheme()
  }

  // 监听系统主题变化（用户未手动设置时）
  const mediaQuery = window.matchMedia?.('(prefers-color-scheme: dark)')
  if (mediaQuery) {
    mediaQuery.addEventListener('change', (e) => {
      if (!localStorage.getItem(THEME_KEY)) {
        isDark.value = e.matches
        applyTheme()
      }
    })
  }

  return { isDark, toggle }
}
