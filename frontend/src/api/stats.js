import request from '@/utils/request'

// v3.6.0：管理端统计
export const adminOverview = () => request.get('/stats/admin/overview')

export const adminRecovery = () => request.get('/stats/admin/recovery')

export const adminPublishTrend = (days = 30) => request.get('/stats/admin/publish-trend', { params: { days } })

export const adminCategoryPie = () => request.get('/stats/admin/category-pie')
