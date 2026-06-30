import request from '@/utils/request'

// 获取待审核列表（分页）
export const getPendingItems = (page, size) =>
  request.get('/admin/reviews', { params: { page, size } })

// 审核物品
export const reviewItem = (id, data) =>
  request.put(`/admin/reviews/${id}`, data)

// 用户管理
export const getUsers = (page, size) =>
  request.get('/admin/users', { params: { page, size } })

export const updateUser = (id, data) =>
  request.put(`/admin/users/${id}`, data)

export const createUser = (data) =>
  request.post('/admin/users', data)

export const deleteUser = (id) =>
  request.delete(`/admin/users/${id}`)

export const batchApprove = (itemIds) =>
  request.post('/admin/reviews/batch-approve', { item_ids: itemIds })