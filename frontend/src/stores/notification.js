import { defineStore } from 'pinia'
import { getUnreadCount } from '@/api/notifications'

export const useNotificationStore = defineStore('notification', {
  state: () => ({
    unreadCount: 0
  }),
  actions: {
    async fetchUnreadCount() {
      try {
        const res = await getUnreadCount()
        this.unreadCount = res.count || 0
      } catch (error) {
        // 如果未登录，忽略错误
        this.unreadCount = 0
      }
    },
    // 增加数量（当收到新消息推送时可调用）
    increment() {
      this.unreadCount++
    },
    // 减少数量（标记已读后调用）
    decrement() {
      if (this.unreadCount > 0) this.unreadCount--
    }
  }
})