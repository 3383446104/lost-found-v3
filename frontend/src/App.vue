<template>
  <AdminLayout v-if="isAdminRoute" />
  <DefaultLayout v-else-if="!isAuthRoute">
    <router-view v-slot="{ Component }">
      <transition name="page" mode="out-in">
        <component :is="Component" />
      </transition>
    </router-view>
  </DefaultLayout>
  <div v-else class="auth-standalone">
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
</style>
