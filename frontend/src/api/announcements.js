import request from '@/utils/request'

export const getAnnouncements = (all = false, params = {}) => request.get('/announcements', {
  params: all ? { all: true, size: 50, ...params } : { size: 20, ...params }
})
export const createAnnouncement = (data) => request.post('/announcements', data)
export const updateAnnouncement = (id, data) => request.put(`/announcements/${id}`, data)
export const deleteAnnouncement = (id) => request.delete(`/announcements/${id}`)
// v3.6.0：草稿/发布流转
export const publishAnnouncement = (id) => request.put(`/announcements/${id}/publish`)
export const unpublishAnnouncement = (id) => request.put(`/announcements/${id}/unpublish`)
// 校园公告改版：详情（访问自增浏览数）/ 富文本配图上传
export const getAnnouncement = (id) => request.get(`/announcements/${id}`)

export const uploadAnnouncementImage = (file) => {
  const formData = new FormData()
  formData.append('image', file)
  return request.post('/announcements/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}
