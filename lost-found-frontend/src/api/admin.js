import request from '@/utils/request'

// 获取待审核列表（分页）
export const getPendingItems = (page, size) =>
  request.get('/admin/reviews', { params: { page, size } })

// 审核物品
export const reviewItem = (id, data) =>
  request.put(`/admin/reviews/${id}`, data)