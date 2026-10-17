<template>
  <div v-if="loading" class="loading-row"><el-skeleton :rows="3" animated /></div>
  <el-empty v-else-if="!reports.length" description="暂无举报记录" />
  <div v-else class="report-list">
    <div v-for="r in reports" :key="r.id" class="report-card">
      <div class="report-head" @click="$router.push(`/items/${r.item_id}`)">
        <span class="report-no">#{{ r.id }}</span>
        <span class="report-item-title">{{ r.item_title }}</span>
        <el-tag :color="REPORT_TYPE_MAP[r.report_type]?.color" effect="dark" size="small">
          {{ REPORT_TYPE_MAP[r.report_type]?.label }}
        </el-tag>
      </div>
      <div class="report-body">
        <p class="report-line">举报原因：{{ r.report_reason }}</p>
        <p class="report-line">提交时间：{{ r.created_at }}</p>
        <div class="report-status-row">
          <el-tag
            :color="REPORT_STATUS_MAP[r.handle_status]?.bg"
            :style="{ color: REPORT_STATUS_MAP[r.handle_status]?.color, border: 'none' }"
          >
            {{ REPORT_STATUS_MAP[r.handle_status]?.label }}
          </el-tag>
          <span v-if="r.handle_time" class="report-time">处理时间：{{ r.handle_time }}</span>
        </div>
        <p v-if="r.handle_result" class="report-line report-line--result">
          处理结论：{{ r.handle_result }}
        </p>
      </div>
    </div>
  </div>

  <el-pagination
    v-if="total > pageSize"
    v-model:current-page="page"
    :page-size="pageSize"
    :total="total"
    layout="prev, pager, next"
    class="pagination-wrap"
    @current-change="load"
  />
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { myReports } from '@/api/reports'
import { REPORT_TYPE_MAP, REPORT_STATUS_MAP } from '@/utils/helpers'

const reports = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 10
const loading = ref(false)

const load = async () => {
  loading.value = true
  try {
    const res = await myReports({ page: page.value, size: pageSize })
    reports.value = res.reports || []
    total.value = res.total || 0
  } catch (e) {
    console.error('加载举报列表失败:', e)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.loading-row { padding: var(--space-6); }

.report-list { display: flex; flex-direction: column; gap: var(--space-4); }

.report-card {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-xs);
}

.report-head {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4);
  cursor: pointer;
  transition: background var(--transition-fast);
}
.report-head:hover { background: var(--neutral-50); }

.report-no { color: var(--text-muted); font-size: var(--text-sm); font-weight: 600; }
.report-item-title { flex: 1; font-weight: 600; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.report-body { padding: 0 var(--space-4) var(--space-4); }
.report-line { margin: 0 0 var(--space-1); font-size: var(--text-sm); color: var(--text-secondary); line-height: 1.6; }
.report-line--result { color: var(--el-color-primary); font-weight: 500; }

.report-status-row { display: flex; align-items: center; gap: var(--space-3); margin: var(--space-2) 0; }
.report-time { font-size: var(--text-xs); color: var(--text-muted); }

.pagination-wrap { display: flex; justify-content: center; margin-top: var(--space-6); }
</style>
