<template>
  <div>
    <!-- 筛选行 -->
    <div class="filter-row">
      <el-input v-model="filters.keyword" placeholder="搜索留言/用户名..." clearable size="small" style="width:220px" @input="onFilter" @clear="onFilter">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-select v-model="filters.status" placeholder="状态" size="small" style="width:120px" clearable @change="onFilter">
        <el-option label="正常" :value="1" />
        <el-option label="已隐藏" :value="0" />
      </el-select>
      <span v-if="total" class="count-hint">共 {{ total }} 条</span>
    </div>

    <div v-loading="loading">
      <el-empty v-if="!loading && !comments.length" description="暂无留言" />
      <el-table v-else :data="comments" stripe style="width:100%">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="物品" min-width="140">
          <template #default="{ row }">
            <router-link :to="`/items/${row.item_id}`" class="item-link">{{ row.item_title }}</router-link>
          </template>
        </el-table-column>
        <el-table-column prop="username" label="用户" width="110" />
        <el-table-column label="内容" min-width="220">
          <template #default="{ row }">
            <el-tag v-if="row.parent_id" size="small" type="info" style="margin-right:6px">回复</el-tag>
            {{ row.content?.substring(0, 60) }}{{ row.content?.length > 60 ? '...' : '' }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 1 ? 'success' : 'info'" size="small">{{ row.status === 1 ? '正常' : '已隐藏' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="时间" width="160" />
        <el-table-column label="操作" width="150" align="center">
          <template #default="{ row }">
            <el-button v-if="row.status === 1" size="small" type="warning" plain @click="setStatus(row, 0)">隐藏</el-button>
            <el-button v-else size="small" type="success" plain @click="setStatus(row, 1)">恢复</el-button>
            <el-button size="small" type="danger" plain @click="remove(row)">删除</el-button>
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
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { adminComments, adminSetCommentStatus, deleteComment } from '@/api/comments'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'

const comments = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 10
const loading = ref(false)
const filters = ref({ keyword: '', status: null })
let timer = null

const load = async () => {
  loading.value = true
  try {
    const params = { page: page.value, size: pageSize }
    const f = filters.value
    if (f.keyword.trim()) params.keyword = f.keyword.trim()
    if (f.status !== null && f.status !== '') params.status = f.status
    const res = await adminComments(params)
    comments.value = res.comments || []
    total.value = res.total || 0
  } catch (e) {
    console.error('加载留言列表失败:', e)
  } finally {
    loading.value = false
  }
}

const onFilter = () => {
  clearTimeout(timer)
  timer = setTimeout(() => { page.value = 1; load() }, 300)
}

const setStatus = async (row, status) => {
  try {
    await adminSetCommentStatus(row.id, status)
    ElMessage.success(status === 0 ? '已隐藏' : '已恢复')
    load()
  } catch (e) {
    console.error('操作失败:', e)
  }
}

const remove = async (row) => {
  try {
    await ElMessageBox.confirm('删除该留言？其下回复将一并删除。', '删除留言', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning'
    })
    await deleteComment(row.id)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    // 用户取消或接口错误（拦截器已提示）
  }
}

onMounted(load)
</script>

<style scoped>
.filter-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: var(--space-3); }
.count-hint { font-size: var(--text-sm); color: var(--text-tertiary); margin-left: auto; }
.item-link { color: var(--el-color-primary); text-decoration: none; font-weight: 500; }
.item-link:hover { text-decoration: underline; }
</style>
