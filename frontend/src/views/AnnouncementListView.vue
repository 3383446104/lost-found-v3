<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">校园公告</h1>
      <p class="page-desc">置顶公告优先展示，其余按发布时间排序</p>
    </div>

    <div class="card ann-list-card" v-loading="loading">
      <el-empty v-if="!loading && !list.length" description="暂无公告" />
      <div v-else class="ann-list">
        <div
          v-for="a in list"
          :key="a.id"
          class="ann-row"
          @click="$router.push(`/announcements/${a.id}`)"
        >
          <el-tag v-if="a.is_pinned" type="warning" size="small" effect="dark">置顶</el-tag>
          <div class="ann-row-main">
            <span class="ann-row-title">{{ a.title }}</span>
            <span class="ann-row-time">{{ a.created_at }} · 浏览 {{ a.view_count ?? 0 }} 次</span>
          </div>
          <el-icon class="ann-row-arrow" :size="14"><ArrowRight /></el-icon>
        </div>
      </div>

      <el-pagination
        v-if="total > size"
        v-model:current-page="page"
        :page-size="size"
        :total="total"
        layout="prev, pager, next"
        class="pagination-wrap"
        @current-change="load"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getAnnouncements } from '@/api/announcements'
import { ArrowRight } from '@element-plus/icons-vue'

const list = ref([])
const total = ref(0)
const page = ref(1)
const size = 10
const loading = ref(false)

const load = async () => {
  loading.value = true
  try {
    const res = await getAnnouncements(false, { page: page.value, size })
    list.value = res.announcements || []
    total.value = res.total || 0
  } catch (e) {
    console.error('加载公告列表失败:', e)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.page-header { margin-bottom: var(--space-5); }
.page-title { margin-bottom: var(--space-1); }
.page-desc { color: var(--text-tertiary); font-size: var(--text-sm); margin: 0; }

.card {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-xs);
}
.ann-list-card { padding: var(--space-4) var(--space-6); }

.ann-list { display: flex; flex-direction: column; }
.ann-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-2);
  border-bottom: 1px solid var(--border-light);
  cursor: pointer;
  transition: background var(--transition-fast);
}
.ann-row:last-child { border-bottom: none; }
.ann-row:hover { background: var(--neutral-50); }

.ann-row-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.ann-row-title {
  font-size: var(--text-base);
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ann-row-time { font-size: var(--text-xs); color: var(--text-tertiary); }
.ann-row-arrow { color: var(--text-muted); flex-shrink: 0; }

.pagination-wrap { display: flex; justify-content: center; margin-top: var(--space-5); }
</style>
