import request from '@/utils/request'

// v3.6.0：举报体系
export const submitReport = (data) => request.post('/reports', data)

export const myReports = (params) => request.get('/reports/mine', { params })

export const adminReports = (params) => request.get('/reports/admin', { params })

export const adminReportDetail = (id) => request.get(`/reports/admin/${id}`)

export const handleReport = (id, data) => request.put(`/reports/admin/${id}/handle`, data)
