import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginView.vue'),
    meta: { requiresGuest: true }
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/RegisterView.vue'),
    meta: { requiresGuest: true }
  },
  {
    path: '/items',
    name: 'Items',
    component: () => import('@/views/HomeView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/items/:id',
    name: 'ItemDetail',
    component: () => import('@/views/ItemDetailView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/hall/lost',
    name: 'HallLost',
    component: () => import('@/views/HomeView.vue'),
    meta: { requiresAuth: true, hallType: 'lost' }
  },
  {
    path: '/hall/found',
    name: 'HallFound',
    component: () => import('@/views/HomeView.vue'),
    meta: { requiresAuth: true, hallType: 'found' }
  },
  {
    path: '/publish',
    name: 'Publish',
    component: () => import('@/views/PublishView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/match',
    name: 'Match',
    component: () => import('@/views/MatchView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/admin',
    component: () => import('@/layouts/AdminLayout.vue'),
    meta: { requiresAuth: true, requiresAdmin: true, layout: 'admin' },
    children: [
      { path: '', redirect: '/admin/items' },
      { path: 'items', name: 'AdminItems', component: () => import('@/views/admin/ItemManage.vue') },
      { path: 'users', name: 'AdminUsers', component: () => import('@/views/admin/UserManage.vue') },
      { path: 'announcements', name: 'AdminAnnouncements', component: () => import('@/views/admin/AnnouncementManage.vue') },
      { path: 'announcements/new', name: 'AdminAnnouncementNew', component: () => import('@/views/admin/AnnouncementEditView.vue') },
      { path: 'announcements/edit', name: 'AdminAnnouncementEdit', component: () => import('@/views/admin/AnnouncementEditView.vue') },
      { path: 'reports', name: 'AdminReports', component: () => import('@/views/admin/ReportManage.vue') },
      { path: 'comments', name: 'AdminComments', component: () => import('@/views/admin/CommentManage.vue') },
      { path: 'banners', name: 'AdminBanners', component: () => import('@/views/admin/BannerManage.vue') },
      { path: 'categories', name: 'AdminCategories', component: () => import('@/views/admin/CategoryManage.vue') },
      { path: 'stats', name: 'AdminStats', component: () => import('@/views/AdminStatsView.vue') }
    ]
  },
  {
    path: '/notifications',
    name: 'Notifications',
    component: () => import('@/views/NotificationsView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/announcements',
    name: 'Announcements',
    component: () => import('@/views/AnnouncementListView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/announcements/:id',
    name: 'AnnouncementDetail',
    component: () => import('@/views/AnnouncementDetailView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/profile',
    name: 'Profile',
    component: () => import('@/views/ProfileView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/claims',
    name: 'Claims',
    component: () => import('@/views/ClaimsView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/reports/mine',
    name: 'MyReports',
    component: () => import('@/views/MyReportsView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/',
    redirect: '/items'
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to, from) => {
  let authStore
  try { authStore = useAuthStore() } catch { return true }
  if (!authStore || !authStore.token) {
    authStore?.restore()
  }
  const isLoggedIn = !!authStore?.token
  const isDisabled = authStore?.user?.status === 'disabled'

  // v3.3: 禁用用户 → 清除登录态 → 跳转登录页
  if (isLoggedIn && isDisabled) {
    authStore.logout()
    return '/login'
  }

  // 需登录但未登录 → /login
  if (to.meta.requiresAuth && !isLoggedIn) {
    return '/login'
  }

  // v3.3: 仅未登录页面但已登录 → 按角色跳转
  if (to.meta.requiresGuest && isLoggedIn) {
    return authStore.isAdmin ? '/admin' : '/items'
  }

  // 需管理员但非管理员 → 首页
  if (to.meta.requiresAdmin && !authStore.isAdmin) {
    return '/items'
  }
})

// 全局后置守卫：刷新未读消息
import { useNotificationStore } from '@/stores/notification'
router.afterEach((to, from) => {
  let authStore
  try { authStore = useAuthStore() } catch { return }
  if (authStore?.token) {
    const notifStore = useNotificationStore()
    notifStore.fetchUnreadCount()
  }
})

export default router