<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">认领中心</h1>
      <p class="page-desc">管理您的认领申请与收到的申请</p>
    </div>

    <ClaimsPanel />
  </div>
</template>

<script setup>
import ClaimsPanel from '@/components/ClaimsPanel.vue'
</script>

<style scoped>
.page-header { margin-bottom: var(--space-5); }
.page-title { margin-bottom: var(--space-1); }
.page-desc { color: var(--text-tertiary); font-size: var(--text-sm); margin: 0; }
</style>
