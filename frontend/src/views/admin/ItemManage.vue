<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">物品管理</h1>
        <p class="page-desc">审核新发布物品，管理在库物品状态与首页推荐位</p>
      </div>
    </div>

    <!-- 筛选行 -->
    <div class="item-filter-row">
      <el-input v-model="itemFilter.keyword" placeholder="搜索标题..." clearable size="small" style="width:180px" @input="onItemFilterChange" @clear="onItemFilterChange">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-select v-model="itemFilter.review" placeholder="审核" size="small" style="width:110px" @change="onItemFilterChange" clearable>
        <el-option label="待审核" value="pending" />
        <el-option label="已通过" value="approved" />
        <el-option label="已驳回" value="rejected" />
      </el-select>
      <el-select v-model="itemFilter.status" placeholder="状态" size="small" style="width:110px" @change="onItemFilterChange" clearable>
        <el-option label="展示中" value="active" />
        <el-option label="认领中" value="claiming" />
        <el-option label="待审核" value="pending" />
        <el-option label="已找回/已归还" value="claimed" />
        <el-option label="已关闭" value="closed" />
        <el-option label="已驳回" value="rejected" />
      </el-select>
      <el-select v-model="itemFilter.type" placeholder="类型" size="small" style="width:90px" @change="onItemFilterChange" clearable>
        <el-option label="失物" value="lost" />
        <el-option label="拾物" value="found" />
      </el-select>
      <span v-if="total" class="item-count">共 {{ total }} 条</span>
    </div>

    <!-- 批量操作工具栏 -->
    <div v-if="items.length && !loading" class="batch-toolbar">
      <el-button type="success" size="small" :disabled="selectedIds.length===0" @click="handleBatch('approve')" :loading="batchLoading">
        通过 ({{ selectedIds.length }})
      </el-button>
      <el-button type="warning" size="small" :disabled="selectedIds.length===0" @click="handleBatch('close')" :loading="batchLoading">
        关闭
      </el-button>
      <el-button type="danger" size="small" :disabled="selectedIds.length===0" @click="handleBatch('delete')" :loading="batchLoading" plain>
        删除
      </el-button>
    </div>

    <el-empty v-if="items.length === 0 && !loading" :description="itemFilter.review==='pending'||!itemFilter.review?'暂无物品':'未找到匹配物品'" />

    <div v-else class="review-table-wrap">
      <el-table :data="items" style="width:100%" stripe row-key="id" @selection-change="handleSelectionChange">
        <el-table-column type="selection" width="44" />
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="expand-content">
              <div class="expand-img" v-if="row.image_path">
                <img :src="getImageUrl(row.image_path)" :alt="row.title" loading="lazy" />
              </div>
              <div v-else class="expand-img img-placeholder">
                <el-icon :size="28"><PictureFilled /></el-icon>
                <span>暂无图片</span>
              </div>
              <div class="expand-info">
                <div class="expand-field"><span class="field-label">描述</span><span class="field-value">{{ row.description || '无描述' }}</span></div>
                <div class="expand-field"><span class="field-label">位置</span><span class="field-value">{{ row.location || '未填写' }}</span></div>
                <div class="expand-field"><span class="field-label">联系方式</span><span class="field-value">{{ row.contact || '未填写' }}</span></div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="id" label="ID" width="60" align="center" />
        <el-table-column label="图片" width="86" align="center">
          <template #default="{ row }">
            <img v-if="row.image_path" :src="getImageUrl(row.image_path)" class="row-thumb" :alt="row.title" loading="lazy" />
            <span v-else class="row-thumb-empty">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="标题" min-width="160">
          <template #default="{ row }"><router-link :to="`/items/${row.id}`" class="item-link">{{ row.title }}</router-link></template>
        </el-table-column>
        <el-table-column prop="type" label="类型" width="80" align="center">
          <template #default="{ row }"><span class="status-tag" :style="{background:ITEM_TYPE_MAP[row.type]?.bg,color:ITEM_TYPE_MAP[row.type]?.color}">{{ ITEM_TYPE_MAP[row.type]?.label }}</span></template>
        </el-table-column>
        <el-table-column prop="review_status" label="审核" width="80" align="center">
          <template #default="{ row }">
            <span v-if="row.review_status==='pending'" style="color:#FF9800">待审核</span>
            <span v-else-if="row.review_status==='approved'" style="color:#4CAF50">已通过</span>
            <span v-else style="color:#E57373">已驳回</span>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.status==='active'" type="success" size="small">展示中</el-tag>
            <el-tag v-else-if="row.status==='claiming'" type="warning" size="small">认领中</el-tag>
            <el-tag v-else-if="row.status==='pending'" type="warning" size="small" effect="plain">待审核</el-tag>
            <el-tag v-else-if="row.status==='claimed'" type="info" size="small">{{ row.type === 'lost' ? '已找回' : '已归还' }}</el-tag>
            <el-tag v-else size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="推荐" width="70" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.is_recommend" size="small" effect="dark" color="#F9A825">推荐</el-tag>
            <span v-else style="color:var(--text-muted);font-size:var(--text-xs)">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="时间" width="160" />
        <el-table-column label="操作" width="200" align="center" fixed="right">
          <template #default="{ row }">
            <template v-if="row.review_status==='pending'">
              <el-button type="success" size="small" @click="approve(row.id)">通过</el-button>
              <el-button type="danger" size="small" @click="reject(row.id)" plain>驳回</el-button>
            </template>
            <template v-else>
              <el-dropdown @command="(cmd) => handleStatusChange(row, cmd)">
                <el-button size="small">改状态<el-icon><ArrowDown /></el-icon></el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="active" v-if="row.status!=='active'">设为展示中</el-dropdown-item>
                    <el-dropdown-item command="closed" v-if="row.status!=='closed'">关闭</el-dropdown-item>
                    <el-dropdown-item command="claimed" v-if="row.status!=='claimed'">{{ row.type === 'lost' ? '标记已找回' : '标记已归还' }}</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </template>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div v-if="total > pageSize" class="pagination-wrap">
      <el-pagination v-model:current-page="page" :page-size="pageSize" :total="total" layout="prev, pager, next" @current-change="loadItems" />
    </div>

    <!-- 驳回对话框 -->
    <el-dialog v-model="dialogVisible" title="驳回物品" width="440px" :close-on-click-modal="false">
      <el-form label-position="top">
        <el-form-item label="驳回理由（必填）">
          <el-input v-model="reason" type="textarea" :rows="4" placeholder="请填写驳回理由..." maxlength="200" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible=false">取消</el-button>
        <el-button type="danger" @click="confirmReject" :loading="rejecting">确认驳回</el-button>
      </template>
    </el-dialog>

  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { reviewItem, getAllItems, updateItemStatus, batchItems } from '@/api/admin'
import { getImageUrl, ITEM_TYPE_MAP } from '@/utils/helpers'
import { ElMessage, ElMessageBox } from 'element-plus'
import { PictureFilled, Search, ArrowDown } from '@element-plus/icons-vue'

const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const dialogVisible = ref(false)
const reason = ref('')
const currentId = ref(null)
const rejecting = ref(false)
// v3.3 批量审核
const selectedIds = ref([])
const batchLoading = ref(false)

// 物品筛选：默认展示所有物品（不预设待审核）
const itemFilter = ref({ keyword: '', review: '', status: '', type: '' })
let itemFilterTimer = null

const loadItems = async () => {
  loading.value = true
  try {
    const f = itemFilter.value
    const params = { page: page.value, size: pageSize.value }
    if (f.keyword.trim()) params.keyword = f.keyword.trim()
    if (f.review) params.review = f.review
    if (f.status) params.item_status = f.status
    if (f.type) params.item_type = f.type
    const res = await getAllItems(params)
    items.value = res.items || []
    total.value = res.total || 0
  } catch (e) {
    console.error('加载物品列表失败', e)
  } finally { loading.value = false }
}

const onItemFilterChange = () => {
  clearTimeout(itemFilterTimer)
  itemFilterTimer = setTimeout(() => { page.value = 1; loadItems() }, 300)
}

const handleStatusChange = async (row, status) => {
  try {
    await updateItemStatus(row.id, status)
    ElMessage.success(`状态已变更`)
    loadItems()
  } catch { }
}

const handleBatch = async (action) => {
  const label = { approve: '批量通过', close: '批量关闭', delete: '批量删除' }[action]
  try {
    if (action === 'delete') {
      await ElMessageBox.confirm(`确认删除已选的 ${selectedIds.value.length} 件物品？此操作不可恢复。`, label, { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'error' })
    }
    batchLoading.value = true
    const res = await batchItems({ ids: selectedIds.value, action })
    ElMessage.success(`${label}完成，影响 ${res.count || selectedIds.value.length} 条`)
    selectedIds.value = []
    loadItems()
  } catch { } finally { batchLoading.value = false }
}

// 审核通过：直接执行（首页推荐位已改为自动展示最近通过物品，不再手动勾选）
const approve = async (id) => {
  try {
    await reviewItem(id, { action: 'approved' })
    ElMessage.success('审核通过，已自动匹配并通知相关用户')
    loadItems()
  } catch {
    // 错误已在拦截器处理
  }
}

const reject = (id) => {
  currentId.value = id
  reason.value = ''
  dialogVisible.value = true
}

const confirmReject = async () => {
  if (!reason.value.trim()) {
    ElMessage.warning('请填写驳回理由')
    return
  }
  rejecting.value = true
  try {
    await reviewItem(currentId.value, { action: 'rejected', reason: reason.value.trim() })
    ElMessage.success('已驳回')
    dialogVisible.value = false
    loadItems()
  } catch {
    // 错误已在拦截器处理
  } finally {
    rejecting.value = false
  }
}

// v3.3: 批量选择（批量操作走 handleBatch → /admin/items/batch）
const handleSelectionChange = (val) => {
  selectedIds.value = val.map(v => v.id)
}

onMounted(loadItems)
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
  flex-wrap: wrap;
  margin-bottom: var(--space-5);
}

.page-header > div:first-child {
  flex: 1;
  min-width: 0;
}

.page-header .page-title {
  margin-bottom: var(--space-1);
}

.item-filter-row {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: var(--space-3);
}

.item-count {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
  margin-left: auto;
}

.review-table-wrap {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  overflow: hidden;
  border: 1px solid var(--border-light);
  box-shadow: var(--shadow-xs);
}

.item-link {
  color: var(--el-color-primary);
  text-decoration: none;
  font-weight: 500;
}

/* 列表行内缩略图 */
.row-thumb {
  width: 60px;
  height: 45px;
  object-fit: cover;
  border-radius: var(--radius-sm, 4px);
  display: block;
  margin: 0 auto;
  border: 1px solid var(--border-light);
}
.row-thumb-empty {
  color: var(--text-muted);
  font-size: var(--text-sm);
}

.item-link:hover {
  text-decoration: underline;
}

/* 展开行 */
.expand-content {
  display: flex;
  gap: var(--space-6);
  padding: var(--space-5) var(--space-6);
  align-items: flex-start;
}

.expand-img {
  width: 160px;
  flex-shrink: 0;
  border-radius: var(--radius-md);
  overflow: hidden;
  background: var(--neutral-100);
  aspect-ratio: 4/3;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--text-muted);
}

.expand-img img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.expand-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.expand-field {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.field-label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-weight: 500;
}

.field-value {
  font-size: var(--text-base);
  color: var(--text-primary);
}

.pagination-wrap {
  display: flex;
  justify-content: center;
  margin-top: var(--space-8);
}

@media (max-width: 640px) {
  .expand-content {
    flex-direction: column;
  }
  .expand-img {
    width: 100%;
  }
}
</style>
