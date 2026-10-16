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
  claiming: { label: '认领中', color: '#FF9800', bg: '#FFF8E1' },
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

// v3.6.0：认领申请状态映射（claims.status 0-4，与后端一致）
export const CLAIM_STATUS_MAP = {
  0: { label: '待审核', color: '#FF9800', bg: '#FFF3E0' },
  1: { label: '已通过', color: '#4CAF50', bg: '#E8F5E9' },
  2: { label: '已拒绝', color: '#E57373', bg: '#FFEBEE' },
  3: { label: '已完成', color: '#2196F3', bg: '#E3F2FD' },
  4: { label: '已撤销', color: '#9E9E9E', bg: '#F5F5F5' }
}

// v3.6.0：举报类型映射（reports.report_type 1-5，与后端一致）
export const REPORT_TYPE_MAP = {
  1: { label: '虚假信息', color: '#E53935' },
  2: { label: '不良内容', color: '#8E24AA' },
  3: { label: '联系方式异常', color: '#FB8C00' },
  4: { label: '重复发布', color: '#3949AB' },
  5: { label: '其他', color: '#757575' }
}

// v3.6.0：举报处理状态映射（reports.handle_status 0-2）
export const REPORT_STATUS_MAP = {
  0: { label: '待处理', color: '#FF9800', bg: '#FFF3E0' },
  1: { label: '已处理', color: '#4CAF50', bg: '#E8F5E9' },
  2: { label: '已驳回', color: '#E57373', bg: '#FFEBEE' }
}

// v3.6.0：证据等级映射（与后端 match_service.LEVEL_TEXT 对齐，仅前端展示用）
export const EVIDENCE_LEVEL_MAP = {
  confirmed: { label: '高度确定', color: '#D32F2F' },
  high_suspect: { label: '高度疑似', color: '#EF6C00' },
  related: { label: '可能相关', color: '#1976D2' },
  reference: { label: '仅供参考', color: '#9E9E9E' }
}

// v3.6.0：命中依据文案（与后端 match_service.BASIS_TEXT 对齐）
export const BASIS_TEXT = {
  image_match: '图像高度一致',
  text_match: '文字描述高度吻合',
  cross_modal: '图片与描述相互印证'
}

// 把依据标识列表翻成中文短句（后端 _basis_text 的前端镜像）
export function basisToText(basis) {
  if (!basis || !basis.length) return ''
  return basis.map((b) => BASIS_TEXT[b] || b).join('、')
}

// 解析物品多图有序列表（images JSON 字符串 → 文件名数组；回退单图）
export function parseItemImages(item) {
  if (item?.images) {
    try {
      const arr = JSON.parse(item.images)
      if (Array.isArray(arr) && arr.length) return arr
    } catch (e) { /* 回退 */ }
  }
  if (item?.image_path) {
    const filename = item.image_path.includes('/') || item.image_path.includes('\\')
      ? item.image_path.split(/[/\\]/).pop()
      : item.image_path
    return [filename]
  }
  return []
}

// 截断文本
export function truncate(text, maxLen = 60) {
  if (!text) return ''
  return text.length > maxLen ? text.slice(0, maxLen) + '...' : text
}
