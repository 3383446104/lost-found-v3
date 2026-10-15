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

// 智能匹配（v3.5.0：响应含 matches[].match_source 与顶层 legend{high,mid}）
// 首页「用一句话描述，帮你找」入口与 MatchView 均复用本函数，不新增端点。
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

// 发布者标记已找回/已认领
export const markClaimed = (id) => request.put(`/items/${id}/mark-claimed`)

// v3.6.0：详情页相似推荐（失物推相似招领 / 招领推相似失物）
export const getSimilar = (id, params) => request.get(`/items/${id}/similar`, { params })

// v3.6.0：首页「为你推荐」（is_recommend 物品）
export const getRecommend = (params) => request.get('/items/recommend', { params })