/**
 * 工具函数集合
 */

// 图片 URL 转换
export function getImageUrl(path) {
  if (!path) return ''
  if (path.startsWith('http')) return path
  const filename = path.includes('/') || path.includes('\\') ? path.split(/[/\\]/).pop() : path
  return `/api/items/uploads/${filename}`
}

// 物品类型映射
export const ITEM_TYPE_MAP = {
  lost: { label: '失物', color: '#E57373', bg: '#FFEBEE' },
  found: { label: '招领', color: '#66BB6A', bg: '#E8F5E9' }
}

// 物品状态映射
export const ITEM_STATUS_MAP = {
  pending: { label: '待审核', color: '#FF9800', bg: '#FFF3E0' },
  active: { label: '展示中', color: '#4CAF50', bg: '#E8F5E9' },
  claimed: { label: '已认领', color: '#2196F3', bg: '#E3F2FD' },
  done: { label: '已完成', color: '#9E9E9E', bg: '#F5F5F5' },
  rejected: { label: '已驳回', color: '#E57373', bg: '#FFEBEE' },
  closed: { label: '已关闭', color: '#9E9E9E', bg: '#F5F5F5' }
}

// 审核状态映射
export const REVIEW_STATUS_MAP = {
  pending: { label: '待审核', color: '#FF9800', bg: '#FFF3E0' },
  approved: { label: '已通过', color: '#4CAF50', bg: '#E8F5E9' },
  rejected: { label: '已驳回', color: '#E57373', bg: '#FFEBEE' }
}

// 格式化时间（后端已返回北京时间字符串，直接使用）
export function formatTime(timeStr) {
  if (!timeStr) return ''
  return timeStr
}

// 截断文本
export function truncate(text, maxLen = 60) {
  if (!text) return ''
  return text.length > maxLen ? text.slice(0, maxLen) + '...' : text
}
