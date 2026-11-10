import axios from 'axios'
import { getToken, setToken } from './storage'
import { ElMessage } from 'element-plus'
import router from '@/router'

const request = axios.create({
  baseURL: '/api',
  timeout: 10000
})

request.interceptors.request.use(config => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 401 单飞标志：并发请求同时 401 时只处理一次（只弹一条提示、只跳一次登录页）
let handling401 = false

request.interceptors.response.use(
  response => {
    // 滑动续期：后端在令牌快过期时通过响应头下发新令牌，这里静默替换
    const renewed = response.headers?.['x-renewed-token']
    if (renewed) {
      setToken(renewed)
    }
    return response.data
  },
  async error => {
    const status = error.response?.status
    const msg = error.response?.data?.detail || error.message || '请求失败'

    // 401 处理：区分「登录失败」与「Token 过期」
    if (status === 401) {
      // 启动校验（silentAuth）：静默失败，由路由守卫直接落到登录页，不弹提示
      if (error.config?.silentAuth) {
        return Promise.reject(error)
      }
      const token = getToken()
      if (token && !handling401) {
        // 有 Token 但 401 → Token 过期
        // 必须走 store.logout()：只 removeToken() 会留下 store.token，
        // 导致路由守卫拦回 /login、轮询继续带空 token 请求（后端回 403）
        handling401 = true
        try {
          const { useAuthStore } = await import('@/stores/auth')
          useAuthStore().logout()
          ElMessage.error('登录已过期，请重新登录')
          await router.replace('/login')
        } finally {
          handling401 = false
        }
      } else if (!token) {
        // 无 Token 的 401 → 登录/注册请求失败（密码错误、用户不存在等）
        ElMessage.error(msg)
      }
      // token 存在但已有一个 401 在处理中 → 静默，避免重复提示
    } else {
      ElMessage.error(msg)
    }
    return Promise.reject(error)
  }
)

export default request