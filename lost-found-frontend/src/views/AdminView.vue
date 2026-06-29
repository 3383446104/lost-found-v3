<template>
  <div class="page-container">
    <div class="page-header">
      <div>
        <h1 class="page-title">审核管理</h1>
        <p class="page-desc">审核用户发布的物品，通过后将自动进行智能匹配并通知相关用户</p>
      </div>
      <span v-if="items.length && !loading" class="pending-count">
        {{ total }} 条待审
      </span>
    </div>

    <!-- 空状态 -->
    <el-empty v-if="items.length === 0 && !loading" description="暂无待审核物品" />

    <!-- 审核表格 -->
    <div v-else class="review-table-wrap">
      <el-table :data="items" style="width:100%" stripe row-key="id">
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
                <div class="expand-field">
                  <span class="field-label">描述</span>
                  <span class="field-value">{{ row.description || '无描述' }}</span>
                </div>
                <div class="expand-field">
                  <span class="field-label">位置</span>
                  <span class="field-value">{{ row.location || '未填写' }}</span>
                </div>
                <div class="expand-field">
                  <span class="field-label">分类</span>
                  <span class="field-value">{{ row.category || '未分类' }}</span>
                </div>
              </div>
              <div class="expand-actions">
                <el-button type="success" @click="approve(row.id)" size="default">
                  <el-icon><Select /></el-icon>通过
                </el-button>
                <el-button type="danger" @click="reject(row.id)" size="default" plain>
                  <el-icon><CloseBold /></el-icon>驳回
                </el-button>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="id" label="ID" width="64" align="center" />
        <el-table-column prop="title" label="标题" min-width="180">
          <template #default="{ row }">
            <router-link :to="`/items/${row.id}`" class="item-link">{{ row.title }}</router-link>
          </template>
        </el-table-column>
        <el-table-column prop="type" label="类型" width="90" align="center">
          <template #default="{ row }">
            <span
              class="status-tag"
              :style="{ background: ITEM_TYPE_MAP[row.type]?.bg, color: ITEM_TYPE_MAP[row.type]?.color }"
            >
              {{ ITEM_TYPE_MAP[row.type]?.label }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="category" label="分类" width="110" />
        <el-table-column prop="created_at" label="发布时间" width="170" />
        <el-table-column label="操作" width="170" align="center" fixed="right">
          <template #default="{ row }">
            <div class="action-btns">
              <el-button type="success" size="small" @click="approve(row.id)">通过</el-button>
              <el-button type="danger" size="small" @click="reject(row.id)" plain>驳回</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 分页 -->
    <div v-if="total > pageSize" class="pagination-wrap">
      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="prev, pager, next"
        @current-change="loadItems"
      />
    </div>

    <!-- 驳回对话框 -->
    <el-dialog v-model="dialogVisible" title="驳回物品" width="440px" :close-on-click-modal="false">
      <el-form label-position="top">
        <el-form-item label="驳回理由（必填）">
          <el-input
            v-model="reason"
            type="textarea"
            :rows="4"
            placeholder="请填写驳回理由，帮助用户修改..."
            maxlength="200"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="danger" @click="confirmReject" :loading="rejecting">确认驳回</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getPendingItems, reviewItem } from '@/api/admin'
import { getImageUrl, ITEM_TYPE_MAP } from '@/utils/helpers'
import { ElMessage } from 'element-plus'
import { PictureFilled, Select, CloseBold } from '@element-plus/icons-vue'

const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const dialogVisible = ref(false)
const reason = ref('')
const currentId = ref(null)
const rejecting = ref(false)

const loadItems = async () => {
  loading.value = true
  try {
    const res = await getPendingItems(page.value, pageSize.value)
    items.value = res.items || []
    total.value = res.total || 0
  } catch (e) {
    console.error('加载审核列表失败', e)
  } finally {
    loading.value = false
  }
}

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

onMounted(loadItems)
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
  flex-wrap: wrap;
}

.page-header .page-title {
  margin-bottom: var(--space-1);
}

.pending-count {
  flex-shrink: 0;
  background: var(--el-color-warning);
  color: white;
  padding: 4px 14px;
  border-radius: var(--radius-full);
  font-size: var(--text-sm);
  font-weight: 600;
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

.item-link:hover {
  text-decoration: underline;
}

.action-btns {
  display: flex;
  gap: 6px;
  justify-content: center;
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

.expand-actions {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  flex-shrink: 0;
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
  .expand-actions {
    flex-direction: row;
    width: 100%;
  }
  .expand-actions .el-button {
    flex: 1;
  }
}
</style>
