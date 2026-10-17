<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">我的举报</h1>
      <p class="page-desc">查看举报处理进度与结果</p>
    </div>

    <MyReportsPanel />
  </div>
</template>

<script setup>
import MyReportsPanel from '@/components/MyReportsPanel.vue'
</script>

<style scoped>
.page-header { margin-bottom: var(--space-5); }
.page-title { margin-bottom: var(--space-1); }
.page-desc { color: var(--text-tertiary); font-size: var(--text-sm); margin: 0; }
</style>
