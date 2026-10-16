<template>
  <div class="skeleton-card">
    <div class="skeleton skeleton-image"></div>
    <div class="skeleton-card-body">
      <div class="skeleton skeleton-title"></div>
      <div class="skeleton skeleton-text"></div>
      <div class="skeleton skeleton-text skeleton-text--short"></div>
    </div>
  </div>
</template>

<script setup>
// 骨架屏卡片 — 可配置 count 数量，支持图片/标题/描述三种占位
defineProps({
  count: {
    type: Number,
    default: 4
  }
})
</script>

<style scoped>
.skeleton-card {
  border-radius: var(--radius-lg);
  overflow: hidden;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
}

.skeleton-image {
  width: 100%;
  aspect-ratio: 4 / 3;
  border-radius: 0;
}

.skeleton-card-body {
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.skeleton-title {
  height: 20px;
  width: 60%;
  margin-bottom: 4px;
}

.skeleton-text {
  height: 14px;
}

.skeleton-text--short {
  width: 40%;
}
</style>
