import request from '@/utils/request'

// v3.6.0：分类管理（管理端）
export const adminCategories = () => request.get('/categories/admin')

export const createCategory = (data) => request.post('/categories/admin', data)

export const updateCategory = (id, data) => request.put(`/categories/admin/${id}`, data)

export const deleteCategory = (id) => request.delete(`/categories/admin/${id}`)
