import request from '@/utils/request'

// 获取待审核列表（分页）
export const getPendingItems = (page, size) =>
  request.get('/admin/reviews', { params: { page, size } })

// 审核物品
export const reviewItem = (id, data) =>
  request.put(`/admin/reviews/${id}`, data)

// 用户管理
export const getUsers = (page, size, keyword = '', includeDeleted = false) =>
  request.get('/admin/users', { params: { page, size, keyword, include_deleted: includeDeleted } })

export const updateUser = (id, data) =>
  request.put(`/admin/users/${id}`, data)

export const createUser = (data) =>
  request.post('/admin/users', data)

export const deleteUser = (id) =>
  request.delete(`/admin/users/${id}`)

export const batchApprove = (itemIds) =>
  request.post('/admin/reviews/batch-approve', { item_ids: itemIds })

// 物品管理（全量+筛选）
export const getAllItems = (params) =>
  request.get('/admin/items', { params })

export const updateItemStatus = (id, status) =>
  request.put(`/admin/items/${id}/status`, { status })

export const batchItems = (data) =>
  request.post('/admin/items/batch', data)