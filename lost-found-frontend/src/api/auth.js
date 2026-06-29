import request from '@/utils/request'

export const login = (data) => request.post('/login', data)
export const register = (data) => request.post('/register', data)
export const getMe = () => request.get('/me')
export const updateProfile = (data) => request.put('/me', data)