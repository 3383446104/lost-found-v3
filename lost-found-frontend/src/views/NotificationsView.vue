<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">
        消息通知
        <span v-if="list.length" class="count-badge">{{ list.length }}</span>
      </h1>
      <el-button
        v-if="list.length"
        size="small"
        @click="markAllAsRead"
        :loading="markingAll"
        text
        type="primary"
        class="read-all-btn"
      >
        <el-icon><Select /></el-icon>
        全部已读
      </el-button>
    </div>

    <!-- 空状态 -->
    <el-empty v-if="list.length === 0 && !loading" description="暂无未读消息">
      <el-button type="primary" @click="$router.push('/items')">去看看物品</el-button>
    </el-empty>

    <!-- 通知列表 -->
    <div v-else class="notif-list">
      <div
        v-for="n in list"
        :key="n.id"
        class="notif-card"
        :class="{ 'has-link': n.link }"
        @click="n.link && $router.push(n.link)"
      >
        <div class="notif-icon">
          <el-icon :size="20"><Bell /></el-icon>
        </div>
        <div class="notif-body">
          <h4 class="notif-title">{{ n.title }}</h4>
          <p class="notif-content">{{ n.content }}</p>
          <span class="notif-time">{{ n.created_at }}</span>
        </div>
        <div class="notif-right">
          <el-button
            size="small"
            @click.stop="markAsRead(n.id)"
            :loading="readingId === n.id"
            text
            type="primary"
            class="read-btn"
          >
            标记已读
          </el-button>
          <el-icon v-if="n.link" class="link-icon"><ArrowRight /></el-icon>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getUnreadList, markRead, markAllRead } from '@/api/notifications'
import { useNotificationStore } from '@/stores/notification'
import { ElMessage } from 'element-plus'
import { Bell, ArrowRight, Select } from '@element-plus/icons-vue'

const list = ref([])
const readingId = ref(null)
const markingAll = ref(false)
const loading = ref(false)
const store = useNotificationStore()

const loadData = async () => {
  loading.value = true
  try {
    const res = await getUnreadList()
    list.value = res.notifications || []
    store.unreadCount = list.value.length
  } catch {
    console.error('加载通知失败')
  } finally {
    loading.value = false
  }
}

const markAsRead = async (id) => {
  readingId.value = id
  try {
    await markRead(id)
    list.value = list.value.filter(n => n.id !== id)
    store.unreadCount = list.value.length
    ElMessage.success('已标记为已读')
  } catch {
    // 错误已在拦截器处理
  } finally {
    readingId.value = null
  }
}

const markAllAsRead = async () => {
  markingAll.value = true
  try {
    const res = await markAllRead()
    ElMessage.success(`已标记 ${res.count || list.value.length} 条消息为已读`)
    list.value = []
    store.unreadCount = 0
  } catch {
    // 拦截器已处理
  } finally {
    markingAll.value = false
  }
}

onMounted(loadData)
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-5);
}

.page-header .page-title {
  margin-bottom: 0;
}

.read-all-btn {
  margin-left: auto;
  flex-shrink: 0;
  font-weight: 500;
}

.count-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  height: 24px;
  padding: 0 7px;
  border-radius: var(--radius-full);
  background: var(--el-color-danger);
  color: white;
  font-size: var(--text-sm);
  font-weight: 700;
  margin-left: var(--space-2);
  vertical-align: middle;
}

.notif-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.notif-card {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  transition: all var(--transition-base);
  box-shadow: var(--shadow-xs);
}

.notif-card.has-link {
  cursor: pointer;
}

.notif-card.has-link:hover {
  box-shadow: var(--shadow-md);
  border-color: var(--el-color-primary-light-4);
  transform: translateY(-1px);
}

.notif-icon {
  width: 44px;
  height: 44px;
  flex-shrink: 0;
  border-radius: var(--radius-full);
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  display: flex;
  align-items: center;
  justify-content: center;
}

.notif-body {
  flex: 1;
  min-width: 0;
}

.notif-title {
  font-size: var(--text-md);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 4px;
  line-height: 1.3;
}

.notif-content {
  font-size: var(--text-base);
  color: var(--text-secondary);
  margin: 0 0 6px;
  line-height: 1.5;
}

.notif-time {
  font-size: var(--text-sm);
  color: var(--text-muted);
}

.notif-right {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  flex-shrink: 0;
}

.read-btn {
  font-size: var(--text-sm);
  font-weight: 500;
}

.link-icon {
  color: var(--text-muted);
  font-size: var(--text-lg);
}

@media (max-width: 640px) {
  .notif-card {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-3);
  }
  .notif-right {
    align-self: flex-end;
  }
}
</style>
