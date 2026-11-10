import { defineStore } from 'pinia'
import { setToken, removeToken, setUser, getUser } from '@/utils/storage'
import { getMe } from '@/api/auth'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: '',
    user: null,
    isAdmin: false
  }),
  actions: {
    setAuth(token, user) {
      this.token = token
      this.user = user
      this.isAdmin = user?.role === 'admin'
      setToken(token)
      setUser(user)
    },
    logout() {
      this.token = ''
      this.user = null
      this.isAdmin = false
      removeToken()
    },
    async fetchUser() {
      try {
        const res = await getMe()
        if (res.user) {
          this.user = res.user
          this.isAdmin = res.user.role === 'admin'
          setUser(res.user)
        }
      } catch {
        this.logout()
      }
    },
    // 启动时会话校验：在渲染任何页面之前确认令牌是否仍然有效
    // （过期 / 后端重启导致 boot 失配 / 账号被禁用）。
    // silentAuth：校验失败不弹「登录已过期」，由路由守卫直接落到登录页。
    // 网络异常（后端未启动）不清凭证，避免误伤。
    async verifySession() {
      if (!this.token) return false
      try {
        const res = await getMe({ silentAuth: true })
        if (res.user) {
          this.user = res.user
          this.isAdmin = res.user.role === 'admin'
          setUser(res.user)
        }
        return true
      } catch (e) {
        const status = e.response?.status
        if (status === 401 || status === 403) {
          this.logout()
          return false
        }
        return true
      }
    },
    // 恢复登录状态（从本地存储）
    restore() {
      const token = localStorage.getItem('access_token')
      const user = getUser()
      if (token && user) {
        this.token = token
        this.user = user
        this.isAdmin = user.role === 'admin'
        return true
      }
      return false
    }
  }
})