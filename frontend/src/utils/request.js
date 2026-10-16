import axios from 'axios'
import { getToken, removeToken } from './storage'
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

request.interceptors.response.use(
  response => response.data,
  error => {
    const status = error.response?.status
    const msg = error.response?.data?.detail || error.message || '请求失败'

    // 401 处理：区分「登录失败」与「Token 过期」
    if (status === 401) {
      const token = getToken()
      if (token) {
        // 有 Token 但 401 → Token 过期
        removeToken()
        router.push('/login')
        ElMessage.error('登录已过期，请重新登录')
      } else {
        // 无 Token 的 401 → 登录/注册请求失败（密码错误、用户不存在等）
        ElMessage.error(msg)
      }
    } else {
      ElMessage.error(msg)
    }
    return Promise.reject(error)
  }
)

export default request