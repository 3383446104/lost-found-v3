<template>
  <div class="layout">
    <!-- ====== 顶部导航栏 ====== -->
    <header class="header">
      <div class="header-inner">
        <!-- Logo -->
        <router-link to="/items" class="logo">
          <span class="logo-icon">
            <svg width="30" height="30" viewBox="0 0 30 30" fill="none">
              <rect width="30" height="30" rx="8" fill="#1B4D3E"/>
              <path d="M15 6c-3.3 0-6 2.7-6 6 0 4 6 10 6 10s6-6 6-10c0-3.3-2.7-6-6-6zm0 8.5c-1.4 0-2.5-1.1-2.5-2.5s1.1-2.5 2.5-2.5 2.5 1.1 2.5 2.5-1.1 2.5-2.5 2.5z" fill="white"/>
              <circle cx="22" cy="8" r="2.5" fill="#D4A853"/>
            </svg>
          </span>
          <span class="logo-text">校园失物寻回</span>
        </router-link>

        <!-- 桌面端导航 -->
        <nav class="nav-desktop">
          <router-link to="/items" class="nav-link" :class="{ active: isActive('/items') }">
            <el-icon :size="18"><Compass /></el-icon>
            <span>发现</span>
          </router-link>
          <router-link to="/publish" class="nav-link" :class="{ active: isActive('/publish') }">
            <el-icon :size="18"><Plus /></el-icon>
            <span>发布</span>
          </router-link>
          <router-link to="/match" class="nav-link" :class="{ active: isActive('/match') }">
            <el-icon :size="18"><Connection /></el-icon>
            <span>智能匹配</span>
          </router-link>
          <router-link to="/notifications" class="nav-link" :class="{ active: isActive('/notifications') }">
            <el-icon :size="18"><Bell /></el-icon>
            <span>消息</span>
            <span v-if="unreadCount > 0" class="nav-badge">
              {{ unreadCount > 99 ? '99+' : unreadCount }}
            </span>
          </router-link>
          <router-link v-if="isAdmin" to="/admin" class="nav-link" :class="{ active: isActive('/admin') }">
            <el-icon :size="18"><Setting /></el-icon>
            <span>审核</span>
          </router-link>
        </nav>

        <!-- 右侧区域 -->
        <div class="header-right">
          <!-- 主题切换 -->
          <button class="theme-btn" @click="toggleTheme" :aria-label="isDark ? '切换到亮色模式' : '切换到暗色模式'">
            <el-icon :size="18"><component :is="isDark ? 'Sunny' : 'Moon'" /></el-icon>
          </button>

          <!-- 用户菜单 -->
          <el-dropdown @command="handleCommand" trigger="click">
            <div class="user-trigger">
              <div class="avatar">
                <span class="avatar-text">{{ (user?.username || 'U')[0].toUpperCase() }}</span>
              </div>
              <span class="user-name">{{ user?.username || '用户' }}</span>
              <el-icon class="chevron" :size="14"><ArrowDown /></el-icon>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">
                  <el-icon><User /></el-icon>个人信息
                </el-dropdown-item>
                <el-dropdown-item command="logout" divided>
                  <el-icon><SwitchButton /></el-icon>退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>

          <!-- 移动端菜单按钮 -->
          <button class="menu-btn" @click="showMobileMenu = !showMobileMenu" :aria-label="showMobileMenu ? '关闭菜单' : '打开菜单'">
            <span class="menu-icon-bar" :class="{ open: showMobileMenu }"></span>
          </button>
        </div>
      </div>

      <!-- 移动端下拉菜单 -->
      <transition name="mobile-menu">
        <nav v-if="showMobileMenu" class="nav-mobile">
          <router-link to="/items" class="nav-link" @click="showMobileMenu = false">
            <el-icon :size="18"><Compass /></el-icon>发现
          </router-link>
          <router-link to="/publish" class="nav-link" @click="showMobileMenu = false">
            <el-icon :size="18"><Plus /></el-icon>发布
          </router-link>
          <router-link to="/match" class="nav-link" @click="showMobileMenu = false">
            <el-icon :size="18"><Connection /></el-icon>智能匹配
          </router-link>
          <router-link to="/notifications" class="nav-link" @click="showMobileMenu = false">
            <el-icon :size="18"><Bell /></el-icon>消息
            <span v-if="unreadCount > 0" class="nav-badge">{{ unreadCount }}</span>
          </router-link>
          <router-link v-if="isAdmin" to="/admin" class="nav-link" @click="showMobileMenu = false">
            <el-icon :size="18"><Setting /></el-icon>审核管理
          </router-link>
        </nav>
      </transition>
    </header>

    <!-- ====== 主内容区 ====== -->
    <main class="main">
      <slot />
    </main>

    <!-- ====== 页脚 ====== -->
    <footer class="footer">
      <div class="footer-inner">
        <div class="footer-left">
          <span class="footer-brand">校园失物智能寻回系统</span>
          <span class="footer-dot">·</span>
          <span class="footer-tagline">让每一件失物都能回家</span>
        </div>
        <span class="footer-copy">© 2026</span>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useNotificationStore } from '@/stores/notification'
import { ElMessage } from 'element-plus'
import {
  Compass, Plus, Connection, Bell, Setting,
  ArrowDown, User, SwitchButton, Moon, Sunny
} from '@element-plus/icons-vue'
import { useTheme } from '@/composables/useTheme'

const { isDark, toggle: toggleTheme } = useTheme()

const authStore = useAuthStore()
const notifStore = useNotificationStore()
const router = useRouter()
const route = useRoute()

const showMobileMenu = ref(false)

const user = computed(() => authStore.user)
const isAdmin = computed(() => authStore.isAdmin)
const unreadCount = computed(() => notifStore.unreadCount)

const isActive = (path) => route.path.startsWith(path)

const refreshUnread = () => {
  if (authStore.token) {
    notifStore.fetchUnreadCount()
  }
}

watch(() => route.path, () => {
  showMobileMenu.value = false
  refreshUnread()
})

let pollTimer = null

onMounted(() => {
  refreshUnread()
  // 每30秒轮询一次未读消息数量
  pollTimer = setInterval(refreshUnread, 30000)
})

// 组件卸载时清除轮询定时器
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})

const handleCommand = (command) => {
  if (command === 'logout') {
    authStore.logout()
    router.push('/login')
    ElMessage.success('已退出登录')
  } else if (command === 'profile') {
    router.push('/profile')
  }
}
</script>

<style scoped>
.layout {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-primary);
}

/* ===================================
   Header — 玻璃拟态 + 微妙底部渐变
   =================================== */
.header {
  position: sticky;
  top: 0;
  z-index: 100;
  background: var(--bg-header);
  backdrop-filter: blur(16px) saturate(180%);
  -webkit-backdrop-filter: blur(16px) saturate(180%);
  border-bottom: 1px solid var(--border-light);
}

/* 底部微妙渐变线 */
.header::after {
  content: '';
  position: absolute;
  bottom: -1px;
  left: 0;
  right: 0;
  height: 1px;
  background: linear-gradient(90deg,
    transparent 0%,
    var(--el-color-primary-light-5) 20%,
    var(--el-color-primary-light-4) 50%,
    var(--el-color-primary-light-5) 80%,
    transparent 100%
  );
  opacity: 0.5;
}

.header-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 var(--space-5);
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

/* ---- Logo ---- */
.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  text-decoration: none;
  flex-shrink: 0;
}

.logo-icon {
  display: flex;
  align-items: center;
  transition: transform var(--transition-fast);
}

.logo:hover .logo-icon {
  transform: scale(1.05);
}

.logo-text {
  font-size: var(--text-lg);
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}

/* ---- Desktop Navigation ---- */
.nav-desktop {
  display: flex;
  align-items: center;
  gap: 2px;
}

.nav-link {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: var(--radius-full);
  text-decoration: none;
  font-size: var(--text-base);
  font-weight: 500;
  color: var(--text-secondary);
  transition: all var(--transition-fast);
  white-space: nowrap;
  position: relative;
}

.nav-link:hover {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.nav-link.active {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  font-weight: 600;
}

/* ---- 通知徽标 ---- */
.nav-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: var(--radius-full);
  background: var(--el-color-danger);
  color: white;
  font-size: var(--text-xs);
  font-weight: 700;
  line-height: 1;
  box-shadow: 0 0 0 2px var(--bg-header);
}

/* ---- Theme Toggle ---- */
.theme-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-full);
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
  flex-shrink: 0;
}

.theme-btn:hover {
  background: var(--neutral-100);
  color: var(--text-primary);
}

/* ---- Header Right ---- */
.header-right {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.user-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 10px 4px 4px;
  border-radius: var(--radius-full);
  transition: background var(--transition-fast);
  user-select: none;
}

.user-trigger:hover {
  background: var(--neutral-100);
}

.avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--el-color-primary), var(--el-color-primary-light-2));
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-base);
  font-weight: 700;
  flex-shrink: 0;
  box-shadow: var(--shadow-xs);
}

.user-name {
  font-size: var(--text-base);
  color: var(--text-primary);
  font-weight: 500;
}

.chevron {
  color: var(--text-tertiary);
  transition: transform var(--transition-fast);
}

.el-dropdown.is-active .chevron {
  transform: rotate(180deg);
}

/* ---- Mobile Menu Button (Hamburger) ---- */
.menu-btn {
  display: none;
  background: none;
  border: none;
  cursor: pointer;
  padding: 8px;
  border-radius: var(--radius-sm);
  width: 36px;
  height: 36px;
  position: relative;
  align-items: center;
  justify-content: center;
  transition: background var(--transition-fast);
}

.menu-btn:hover {
  background: var(--neutral-100);
}

.menu-icon-bar {
  display: block;
  width: 18px;
  height: 2px;
  background: var(--text-primary);
  border-radius: 1px;
  transition: all var(--transition-base);
  position: relative;
}

.menu-icon-bar::before,
.menu-icon-bar::after {
  content: '';
  position: absolute;
  left: 0;
  width: 18px;
  height: 2px;
  background: var(--text-primary);
  border-radius: 1px;
  transition: all var(--transition-base);
}

.menu-icon-bar::before { top: -5px; }
.menu-icon-bar::after  { top: 5px; }

.menu-icon-bar.open {
  background: transparent;
}

.menu-icon-bar.open::before {
  top: 0;
  transform: rotate(45deg);
}

.menu-icon-bar.open::after {
  top: 0;
  transform: rotate(-45deg);
}

/* ---- Mobile Navigation ---- */
.nav-mobile {
  display: none;
  flex-direction: column;
  padding: var(--space-3) var(--space-5) var(--space-5);
  background: var(--bg-card);
  border-top: 1px solid var(--border-light);
  box-shadow: var(--shadow-md);
}

.nav-mobile .nav-link {
  padding: 12px 16px;
  font-size: var(--text-md);
  border-radius: var(--radius-md);
}

.nav-mobile .nav-badge {
  box-shadow: 0 0 0 2px var(--bg-card);
}

/* Mobile menu transition */
.mobile-menu-enter-active,
.mobile-menu-leave-active {
  transition: all 0.25s ease;
}

.mobile-menu-enter-from,
.mobile-menu-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

/* ===================================
   Main Content
   =================================== */
.main {
  flex: 1;
}

/* ===================================
   Footer
   =================================== */
.footer {
  background: var(--bg-card);
  border-top: 1px solid var(--border-light);
  padding: var(--space-5);
  margin-top: var(--space-12);
}

.footer-inner {
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

.footer-left {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.footer-brand {
  font-weight: 600;
  color: var(--text-secondary);
}

.footer-dot {
  color: var(--border-strong);
}

.footer-copy {
  color: var(--text-muted);
}

/* ===================================
   Responsive
   =================================== */
@media (max-width: 768px) {
  .nav-desktop {
    display: none;
  }

  .menu-btn {
    display: flex;
  }

  .nav-mobile {
    display: flex;
  }

  .user-name {
    display: none;
  }
}

@media (max-width: 480px) {
  .logo-text {
    font-size: var(--text-md);
  }

  .footer-left {
    flex-direction: column;
    gap: 2px;
    align-items: flex-start;
  }

  .footer-dot {
    display: none;
  }
}
</style>
