import request from '@/utils/request'

// v3.6.0：认领闭环
export const uploadProof = (file) => {
  const formData = new FormData()
  formData.append('image', file)
  return request.post('/claims/proof-upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

export const applyClaim = (data) => request.post('/claims', data)

export const myClaims = (params) => request.get('/claims/mine', { params })

export const receivedClaims = (params) => request.get('/claims/received', { params })

export const claimStatus = (itemId) => request.get(`/claims/status/${itemId}`)

export const getClaim = (id) => request.get(`/claims/${id}`)

export const approveClaim = (id) => request.post(`/claims/${id}/approve`)

export const rejectClaim = (id, reviewRemark) => request.post(`/claims/${id}/reject`, { review_remark: reviewRemark })

export const completeClaim = (id) => request.post(`/claims/${id}/complete`)

export const cancelClaim = (id) => request.post(`/claims/${id}/cancel`)
