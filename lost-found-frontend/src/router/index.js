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
    name: 'Admin',
    component: () => import('@/views/AdminView.vue'),
    meta: { requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/notifications',
    name: 'Notifications',
    component: () => import('@/views/NotificationsView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/profile',
    name: 'Profile',
    component: () => import('@/views/ProfileView.vue'),
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

router.beforeEach((to, from, next) => {
  const authStore = useAuthStore()
  if (!authStore.token) {
    authStore.restore()
  }
  const isLoggedIn = !!authStore.token
  if (to.meta.requiresAuth && !isLoggedIn) {
    next('/login')
  } else if (to.meta.requiresGuest && isLoggedIn) {
    next('/')
  } else if (to.meta.requiresAdmin && !authStore.isAdmin) {
    next('/')
  } else {
    next()
  }
})

// 全局后置守卫：刷新未读消息
import { useNotificationStore } from '@/stores/notification'
router.afterEach((to, from) => {
  const authStore = useAuthStore()
  if (authStore.token) {
    const notifStore = useNotificationStore()
    notifStore.fetchUnreadCount()
  }
})

export default router