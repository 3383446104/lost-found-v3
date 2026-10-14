import request from '@/utils/request'

// v3.6.0：留言互动
export const listComments = (itemId) => request.get(`/comments/item/${itemId}`)

export const postComment = (data) => request.post('/comments', data)

export const deleteComment = (id) => request.delete(`/comments/${id}`)

export const adminSetCommentStatus = (id, status) => request.put(`/comments/admin/${id}/status`, { status })

export const adminComments = (params) => request.get('/comments/admin', { params })
