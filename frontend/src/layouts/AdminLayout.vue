<template>
  <div class="admin-layout">
    <!-- 独立后台侧边栏 -->
    <aside class="admin-sidebar">
      <div class="admin-brand">
        <el-icon :size="20"><Monitor /></el-icon>
        <span>管理后台</span>
      </div>
      <nav class="admin-nav">
        <router-link
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="admin-nav-item"
          :class="{ active: isActive(item.to) }"
        >
          <el-icon :size="16"><component :is="item.icon" /></el-icon>
          <span class="admin-nav-label">{{ item.label }}</span>
          <span v-if="item.to === '/admin/items' && pendingCount > 0" class="nav-badge">{{ pendingCount }}</span>
        </router-link>
      </nav>
      <div class="admin-sidebar-footer">
        <router-link to="/items" class="admin-nav-item">
          <el-icon :size="16"><HomeFilled /></el-icon>
          <span class="admin-nav-label">返回用户端</span>
        </router-link>
        <a class="admin-nav-item" @click="handleLogout">
          <el-icon :size="16"><SwitchButton /></el-icon>
          <span class="admin-nav-label">退出登录</span>
        </a>
      </div>
    </aside>

    <!-- 内容区 -->
    <main class="admin-main">
      <router-view v-slot="{ Component }">
        <transition name="page" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { adminOverview } from '@/api/stats'
import {
  TrendCharts, Goods, User, Bell, WarningFilled, ChatDotRound,
  Picture, Menu, HomeFilled, SwitchButton, Monitor,
} from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const pendingCount = ref(0)

const navItems = [
  { to: '/admin/stats', label: '数据统计', icon: TrendCharts },
  { to: '/admin/items', label: '物品管理', icon: Goods },
  { to: '/admin/users', label: '用户管理', icon: User },
  { to: '/admin/announcements', label: '公告管理', icon: Bell },
  { to: '/admin/reports', label: '举报管理', icon: WarningFilled },
  { to: '/admin/comments', label: '留言管理', icon: ChatDotRound },
  { to: '/admin/banners', label: '轮播图', icon: Picture },
  { to: '/admin/categories', label: '分类管理', icon: Menu },
]

const isActive = (to) => route.path === to

// 待审核数红点（复用通知未读的 30s 轮询模式）
const refreshPending = async () => {
  try {
    const res = await adminOverview()
    const d = res.data || res
    pendingCount.value = d.pending_review ?? 0
  } catch {
    pendingCount.value = 0
  }
}

let timer = null
onMounted(() => {
  refreshPending()
  timer = setInterval(refreshPending, 30000)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
})

const handleLogout = () => {
  authStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.admin-layout {
  display: flex;
  min-height: 100vh;
  background: var(--bg-page, #f5f7fa);
}

/* ---- 侧边栏 ---- */
.admin-sidebar {
  width: 216px;
  flex-shrink: 0;
  background: #1f2937;
  color: #d1d5db;
  display: flex;
  flex-direction: column;
  position: sticky;
  top: 0;
  height: 100vh;
}

.admin-brand {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-5) var(--space-4);
  color: #fff;
  font-weight: 700;
  font-size: var(--text-md);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.admin-nav {
  flex: 1;
  padding: var(--space-3) 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.admin-nav-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: 10px var(--space-4);
  color: #d1d5db;
  text-decoration: none;
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--transition-base);
  border-left: 3px solid transparent;
}

.admin-nav-item:hover {
  background: rgba(255, 255, 255, 0.06);
  color: #fff;
}

.admin-nav-item.active {
  background: rgba(64, 158, 255, 0.14);
  color: #79bbff;
  border-left-color: #409eff;
}

.admin-nav-label {
  flex: 1;
}

.nav-badge {
  background: #f56c6c;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  min-width: 18px;
  height: 18px;
  line-height: 18px;
  padding: 0 5px;
  border-radius: 9px;
  text-align: center;
}

.admin-sidebar-footer {
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  padding: var(--space-3) 0;
}

/* ---- 内容区 ---- */
.admin-main {
  flex: 1;
  min-width: 0;
  padding: var(--space-6);
}

@media (max-width: 768px) {
  .admin-layout {
    flex-direction: column;
  }
  .admin-sidebar {
    width: 100%;
    height: auto;
    position: static;
    flex-direction: row;
    align-items: center;
    overflow-x: auto;
  }
  .admin-brand {
    display: none;
  }
  .admin-nav {
    flex-direction: row;
    padding: 0 var(--space-2);
    gap: 0;
  }
  .admin-nav-item {
    border-left: none;
    border-bottom: 2px solid transparent;
    white-space: nowrap;
  }
  .admin-nav-item.active {
    border-bottom-color: #409eff;
  }
  .admin-sidebar-footer {
    border-top: none;
    padding: 0 var(--space-2);
  }
  .admin-main {
    padding: var(--space-4);
  }
}
</style>
