import request from '@/utils/request'

export const getAnnouncements = (all = false) => request.get('/announcements', { params: all ? { all: true, size: 50 } : { size: 20 } })
export const createAnnouncement = (data) => request.post('/announcements', data)
export const updateAnnouncement = (id, data) => request.put(`/announcements/${id}`, data)
export const deleteAnnouncement = (id) => request.delete(`/announcements/${id}`)
