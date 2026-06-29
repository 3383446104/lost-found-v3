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