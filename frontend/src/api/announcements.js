import request from '@/utils/request'

export const getAnnouncements = (all = false) => request.get('/announcements', { params: all ? { all: true, size: 50 } : { size: 20 } })
export const createAnnouncement = (data) => request.post('/announcements', data)
export const updateAnnouncement = (id, data) => request.put(`/announcements/${id}`, data)
export const deleteAnnouncement = (id) => request.delete(`/announcements/${id}`)
// v3.6.0：草稿/发布流转
export const publishAnnouncement = (id) => request.put(`/announcements/${id}/publish`)
export const unpublishAnnouncement = (id) => request.put(`/announcements/${id}/unpublish`)
// v3.7.0：公告详情（访问自增浏览数）/ 封面上传
export const getAnnouncement = (id) => request.get(`/announcements/${id}`)

export const uploadAnnouncementImage = (file) => {
  const formData = new FormData()
  formData.append('image', file)
  return request.post('/announcements/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}
