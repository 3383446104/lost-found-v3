import request from '@/utils/request'

export const login = (data) => request.post('/login', data)
export const register = (data) => request.post('/register', data)
export const getMe = () => request.get('/me')
export const updateProfile = (data) => request.put('/me', data)
export const getHistory = () => request.get('/me/history')
export const deleteAccount = () => request.delete('/me')
// 头像上传（avatar_ 前缀，复用 items/uploads 静态路由）
export const uploadAvatar = (file) => {
  const formData = new FormData()
  formData.append('image', file)
  return request.post('/me/avatar', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}