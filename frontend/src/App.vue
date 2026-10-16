<template>
  <DefaultLayout v-if="!isAuthRoute">
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

const route = useRoute()

const isAuthRoute = computed(() => !!route.meta.requiresGuest)
</script>

<style>
.auth-standalone {
  min-height: 100vh;
}
</style>
