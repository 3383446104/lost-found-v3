<template>
  <div class="page-container">
    <div class="card ann-detail-card" v-loading="loading">
      <div v-if="!loading && ann">
        <router-link to="/announcements" class="back-link">← 返回校园公告</router-link>
        <div class="ann-detail-head">
          <div class="ann-detail-title-row">
            <el-tag v-if="ann.is_pinned" type="warning" size="small" effect="dark">置顶</el-tag>
            <h1 class="ann-title">{{ ann.title }}</h1>
          </div>
          <p class="ann-meta">发布时间：{{ ann.created_at }} · 浏览 {{ ann.view_count ?? 0 }} 次</p>
        </div>
        <div class="ann-divider"></div>
        <!-- 富文本内容（管理员编辑的图文排版） -->
        <div class="ann-content" v-html="ann.content"></div>
      </div>
      <el-empty v-else-if="!loading" description="公告不存在或已下架" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { getAnnouncement } from '@/api/announcements'

const route = useRoute()
const ann = ref(null)
const loading = ref(false)

onMounted(async () => {
  loading.value = true
  try {
    const res = await getAnnouncement(route.params.id)
    ann.value = res.announcement || null
  } catch {
    ann.value = null
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.card {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-xs);
}
.ann-detail-card {
  padding: var(--space-6);
  max-width: 860px;
  margin: 0 auto;
}

.back-link {
  font-size: var(--text-sm);
  color: var(--el-color-primary);
  text-decoration: none;
}
.back-link:hover { text-decoration: underline; }

.ann-detail-head { margin-top: var(--space-4); }
.ann-detail-title-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}
.ann-title {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}
.ann-meta { font-size: var(--text-sm); color: var(--text-tertiary); margin: var(--space-2) 0 0; }

.ann-divider {
  height: 1px;
  background: var(--border-light);
  margin: var(--space-5) 0;
}

/* 富文本内容排版 */
.ann-content {
  font-size: var(--text-base);
  color: var(--text-primary);
  line-height: 1.9;
  word-break: break-word;
}
.ann-content :deep(img) {
  max-width: 100%;
  border-radius: var(--radius-md);
  display: block;
  margin: var(--space-3) auto;
}
.ann-content :deep(h1),
.ann-content :deep(h2),
.ann-content :deep(h3),
.ann-content :deep(h4) {
  margin: var(--space-4) 0 var(--space-2);
  line-height: 1.4;
}
.ann-content :deep(p) { margin: 0 0 var(--space-3); }
.ann-content :deep(blockquote) {
  border-left: 3px solid var(--el-color-primary);
  padding-left: var(--space-3);
  color: var(--text-secondary);
  margin: var(--space-3) 0;
}
.ann-content :deep(pre) {
  background: var(--neutral-50);
  padding: var(--space-3);
  border-radius: var(--radius-md);
  overflow-x: auto;
}
.ann-content :deep(a) { color: var(--el-color-primary); }
</style>
