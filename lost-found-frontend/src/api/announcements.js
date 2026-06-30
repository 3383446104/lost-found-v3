import request from '@/utils/request'

export const getAnnouncements = () => request.get('/announcements')
export const createAnnouncement = (data) => request.post('/announcements', data)
export const updateAnnouncement = (id, data) => request.put(`/announcements/${id}`, data)
export const deleteAnnouncement = (id) => request.delete(`/announcements/${id}`)
