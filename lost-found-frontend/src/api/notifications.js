import request from '@/utils/request'

export const getUnreadCount = () => request.get('/notifications/unread/count')
export const getUnreadList = () => request.get('/notifications/unread')
export const markRead = (id) => request.put(`/notifications/${id}/read`)