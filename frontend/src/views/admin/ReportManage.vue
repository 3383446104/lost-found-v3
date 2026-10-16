<template>
  <div>
    <!-- 筛选行 -->
    <div class="filter-row">
      <el-input v-model="filters.keyword" placeholder="搜索物品/原因/举报人..." clearable size="small" style="width:220px" @input="onFilter" @clear="onFilter">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-select v-model="filters.report_type" placeholder="举报类型" size="small" style="width:130px" clearable @change="onFilter">
        <el-option v-for="(v, k) in REPORT_TYPE_MAP" :key="k" :label="v.label" :value="Number(k)" />
      </el-select>
      <el-select v-model="filters.handle_status" placeholder="处理状态" size="small" style="width:120px" clearable @change="onFilter">
        <el-option label="待处理" :value="0" />
        <el-option label="已处理" :value="1" />
        <el-option label="已驳回" :value="2" />
      </el-select>
      <span v-if="total" class="count-hint">共 {{ total }} 条</span>
    </div>

    <div v-loading="loading">
      <el-empty v-if="!loading && !reports.length" description="暂无举报" />
      <el-table v-else :data="reports" stripe style="width:100%">
        <el-table-column prop="id" label="编号" width="70" />
        <el-table-column label="物品" min-width="160">
          <template #default="{ row }">
            <router-link :to="`/items/${row.item_id}`" class="item-link">{{ row.item_title }}</router-link>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="110">
          <template #default="{ row }">
            <el-tag :color="REPORT_TYPE_MAP[row.report_type]?.color" effect="dark" size="small">
              {{ REPORT_TYPE_MAP[row.report_type]?.label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="report_reason" label="原因" min-width="180">
          <template #default="{ row }">{{ row.report_reason?.substring(0, 50) }}{{ row.report_reason?.length > 50 ? '...' : '' }}</template>
        </el-table-column>
        <el-table-column prop="reporter_username" label="举报人" width="110" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag
              :color="REPORT_STATUS_MAP[row.handle_status]?.bg"
              :style="{ color: REPORT_STATUS_MAP[row.handle_status]?.color, border: 'none' }"
              size="small"
            >
              {{ REPORT_STATUS_MAP[row.handle_status]?.label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="时间" width="160" />
        <el-table-column label="操作" width="100" align="center">
          <template #default="{ row }">
            <el-button v-if="row.handle_status === 0" type="primary" size="small" @click="openDetail(row)">处理</el-button>
            <el-button v-else size="small" @click="openDetail(row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        v-if="total > pageSize"
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="prev, pager, next"
        style="margin-top:16px;justify-content:center"
        @current-change="load"
      />
    </div>

    <!-- 并排详情 + 处理对话框 -->
    <el-dialog v-model="detailVisible" title="举报详情" width="640px" :close-on-click-modal="false">
      <template v-if="detail">
        <div class="two-col">
          <div class="col">
            <h4 class="col-title">举报内容</h4>
            <p class="col-line"><strong>类型：</strong>{{ REPORT_TYPE_MAP[detail.report.report_type]?.label }}</p>
            <p class="col-line"><strong>原因：</strong>{{ detail.report.report_reason }}</p>
            <p class="col-line"><strong>举报人：</strong>{{ detail.report.reporter_username }}</p>
            <p class="col-line"><strong>时间：</strong>{{ detail.report.created_at }}</p>
            <p v-if="detail.report.handle_result" class="col-line"><strong>处理结论：</strong>{{ detail.report.handle_result }}</p>
            <p v-if="detail.report.handler_username" class="col-line"><strong>处理人：</strong>{{ detail.report.handler_username }}</p>
          </div>
          <div class="col" v-if="detail.item">
            <h4 class="col-title">被举报物品</h4>
            <p class="col-line"><strong>标题：</strong>{{ detail.item.title }}</p>
            <p class="col-line"><strong>类型：</strong>{{ detail.item.type === 'lost' ? '失物' : '招领' }}（{{ detail.item.status }} / {{ detail.item.review_status }}）</p>
            <p class="col-line"><strong>描述：</strong>{{ detail.item.description || '无' }}</p>
            <p class="col-line"><strong>位置：</strong>{{ detail.item.location || '未填写' }}</p>
            <p class="col-line"><strong>联系方式：</strong>{{ detail.item.contact || '未填写' }}</p>
          </div>
        </div>
        <div v-if="detail.report.handle_status === 0" class="handle-box">
          <h4 class="col-title">处理举报</h4>
          <el-radio-group v-model="handleForm.handle_status">
            <el-radio :value="1">已处理</el-radio>
            <el-radio :value="2">驳回举报</el-radio>
          </el-radio-group>
          <el-input
            v-model="handleForm.handle_result"
            type="textarea"
            :rows="3"
            maxlength="500"
            show-word-limit
            placeholder="处理结论（必填，将通知举报人）"
            style="margin-top:10px"
          />
          <div style="margin-top:12px;text-align:right">
            <el-button @click="detailVisible = false">取消</el-button>
            <el-button type="primary" @click="submitHandle" :loading="handling">提交处理</el-button>
          </div>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { adminReports, adminReportDetail, handleReport } from '@/api/reports'
import { REPORT_TYPE_MAP, REPORT_STATUS_MAP } from '@/utils/helpers'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'

const reports = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 10
const loading = ref(false)
const filters = ref({ keyword: '', report_type: null, handle_status: null })
let timer = null

const detailVisible = ref(false)
const detail = ref(null)
const handling = ref(false)
const handleForm = ref({ handle_status: 1, handle_result: '' })

const load = async () => {
  loading.value = true
  try {
    const params = { page: page.value, size: pageSize }
    const f = filters.value
    if (f.keyword.trim()) params.keyword = f.keyword.trim()
    if (f.report_type !== null && f.report_type !== '') params.report_type = f.report_type
    if (f.handle_status !== null && f.handle_status !== '') params.handle_status = f.handle_status
    const res = await adminReports(params)
    reports.value = res.reports || []
    total.value = res.total || 0
  } catch (e) {
    console.error('加载举报列表失败:', e)
  } finally {
    loading.value = false
  }
}

const onFilter = () => {
  clearTimeout(timer)
  timer = setTimeout(() => { page.value = 1; load() }, 300)
}

const openDetail = async (row) => {
  try {
    detail.value = await adminReportDetail(row.id)
    handleForm.value = { handle_status: 1, handle_result: '' }
    detailVisible.value = true
  } catch (e) {
    console.error('加载举报详情失败:', e)
  }
}

const submitHandle = async () => {
  if (!handleForm.value.handle_result.trim()) {
    ElMessage.warning('请填写处理结论')
    return
  }
  handling.value = true
  try {
    await handleReport(detail.value.report.id, handleForm.value)
    ElMessage.success('处理完成，已通知举报人')
    detailVisible.value = false
    load()
  } catch (e) {
    console.error('处理失败:', e)
  } finally {
    handling.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.filter-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: var(--space-3); }
.count-hint { font-size: var(--text-sm); color: var(--text-tertiary); margin-left: auto; }
.item-link { color: var(--el-color-primary); text-decoration: none; font-weight: 500; }
.item-link:hover { text-decoration: underline; }

.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-4); }
.col { border: 1px solid var(--border-light); border-radius: var(--radius-md); padding: var(--space-4); background: var(--neutral-50); }
.col-title { margin: 0 0 var(--space-2); font-size: var(--text-sm); font-weight: 700; color: var(--text-primary); }
.col-line { margin: 0 0 4px; font-size: var(--text-sm); color: var(--text-secondary); line-height: 1.6; word-break: break-all; }
.handle-box { margin-top: var(--space-4); border-top: 1px solid var(--border-light); padding-top: var(--space-4); }

@media (max-width: 640px) {
  .two-col { grid-template-columns: 1fr; }
}
</style>
