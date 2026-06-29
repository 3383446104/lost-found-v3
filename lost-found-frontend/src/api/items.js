import request from '@/utils/request'

// 发布物品（FormData）
export const createItem = (formData) => request.post('/items/', formData, {
  headers: { 'Content-Type': 'multipart/form-data' }
})

// 获取列表（支持分页、筛选）
export const getItems = (params) => request.get('/items/', { params })

// 获取详情
export const getItem = (id) => request.get(`/items/${id}`)

// 更新物品（FormData）
export const updateItem = (id, formData) => request.put(`/items/${id}`, formData, {
  headers: { 'Content-Type': 'multipart/form-data' }
})

// 删除物品
export const deleteItem = (id) => request.delete(`/items/${id}`)

// 智能匹配
export const matchItems = (data) => request.post('/items/match', data)

// 临时上传
export const tempUpload = (file) => {
  const formData = new FormData()
  formData.append('image', file)
  return request.post('/items/temp-upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

// 获取类别
export const getCategories = () => request.get('/items/categories')

// 认领物品
export const claimItem = (id) => request.post(`/items/${id}/claim`)

// 确认/拒绝认领
export const confirmClaim = (id, data) => request.put(`/items/${id}/claim/confirm`, data)