import request from '@/utils/request'

export const getAnnouncements = (all = false) => request.get('/announcements', { params: all ? { all: true, size: 50 } : { size: 20 } })
export const createAnnouncement = (data) => request.post('/announcements', data)
export const updateAnnouncement = (id, data) => request.put(`/announcements/${id}`, data)
export const deleteAnnouncement = (id) => request.delete(`/announcements/${id}`)
// v3.6.0：草稿/发布流转
export const publishAnnouncement = (id) => request.put(`/announcements/${id}/publish`)
export const unpublishAnnouncement = (id) => request.put(`/announcements/${id}/unpublish`)
