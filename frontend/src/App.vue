<template>
  <DefaultLayout v-if="!isAuthRoute && !isAdminRoute">
    <router-view v-slot="{ Component }">
      <transition name="page" mode="out-in">
        <component :is="Component" />
      </transition>
    </router-view>
  </DefaultLayout>
  <div v-else-if="isAuthRoute" class="auth-standalone">
    <router-view v-slot="{ Component }">
      <transition name="page" mode="out-in">
        <component :is="Component" />
      </transition>
    </router-view>
  </div>
  <!-- 后台路由：经本 router-view 渲染 AdminLayout（其内部 router-view 深度+1 渲染子页面） -->
  <div v-else class="admin-standalone">
    <router-view v-slot="{ Component }">
      <transition name="page" mode="out-in">
        <component :is="Component" />
      </transition>
    </router-view>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import DefaultLayout from '@/layouts/DefaultLayout.vue'
import AdminLayout from '@/layouts/AdminLayout.vue'

const route = useRoute()

const isAuthRoute = computed(() => !!route.meta.requiresGuest)
// 独立后台布局：/admin 父路由 meta.layout === 'admin'
const isAdminRoute = computed(() => route.meta.layout === 'admin')
</script>

<style>
.auth-standalone {
  min-height: 100vh;
}

.admin-standalone {
  min-height: 100vh;
}
</style>
