import request from '@/utils/request'

// v3.6.0：轮播图
export const publicBanners = () => request.get('/banners')

export const uploadBanner = (file) => {
  const formData = new FormData()
  formData.append('image', file)
  return request.post('/banners/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

export const adminBanners = () => request.get('/banners/admin')

export const createBanner = (data) => request.post('/banners/admin', data)

export const updateBanner = (id, data) => request.put(`/banners/admin/${id}`, data)

export const deleteBanner = (id) => request.delete(`/banners/admin/${id}`)
