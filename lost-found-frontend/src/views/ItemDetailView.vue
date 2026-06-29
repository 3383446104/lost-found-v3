<template>
  <div class="page-container">
    <div v-if="item" class="detail-layout">
      <!-- 返回按钮 -->
      <div class="back-row">
        <el-button :icon="ArrowLeft" @click="$router.back()" class="back-btn" text>
          返回
        </el-button>
      </div>

      <!-- 图片区域 -->
      <div class="detail-hero">
        <div class="hero-img-wrapper">
          <img
            v-if="item.image_path"
            :src="getImageUrl(item.image_path)"
            :alt="item.title"
            class="hero-img"
          />
          <div v-else class="img-placeholder hero-img">
            <el-icon :size="56"><PictureFilled /></el-icon>
            <span>暂无图片</span>
          </div>
        </div>
      </div>

      <!-- 信息区域 -->
      <div class="detail-info">
        <div class="info-header">
          <div class="info-tags">
            <span
              class="status-tag"
              :style="{ background: ITEM_TYPE_MAP[item.type]?.bg, color: ITEM_TYPE_MAP[item.type]?.color }"
            >
              {{ ITEM_TYPE_MAP[item.type]?.label }}
            </span>
            <span
              class="status-tag"
              :style="{ background: ITEM_STATUS_MAP[item.status]?.bg, color: ITEM_STATUS_MAP[item.status]?.color }"
            >
              {{ ITEM_STATUS_MAP[item.status]?.label }}
            </span>
            <span
              v-if="item.review_status"
              class="status-tag"
              :style="{ background: REVIEW_STATUS_MAP[item.review_status]?.bg, color: REVIEW_STATUS_MAP[item.review_status]?.color }"
            >
              审核: {{ REVIEW_STATUS_MAP[item.review_status]?.label }}
            </span>
          </div>
          <h1 class="item-title">{{ item.title }}</h1>
        </div>

        <!-- 驳回理由 -->
        <div v-if="item.review_status === 'rejected' && item.reject_reason" class="reject-box">
          <el-icon :size="18"><WarningFilled /></el-icon>
          <span><strong>驳回理由：</strong>{{ item.reject_reason }}</span>
        </div>

        <!-- 描述 -->
        <div class="info-section" v-if="item.description">
          <h3 class="section-title">详细描述</h3>
          <p class="info-text">{{ item.description }}</p>
        </div>

        <!-- 基本信息 -->
        <div class="info-section">
          <h3 class="section-title">基本信息</h3>
          <div class="info-grid">
            <div class="info-item">
              <span class="info-label">分类</span>
              <span class="info-value">{{ item.category || '未分类' }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">位置</span>
              <span class="info-value">{{ item.location || '未填写' }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">发布时间</span>
              <span class="info-value">{{ item.created_at }}</span>
            </div>
            <div class="info-item" v-if="item.review_time">
              <span class="info-label">审核时间</span>
              <span class="info-value">{{ item.review_time }}</span>
            </div>
          </div>
        </div>

        <!-- 联系方式 -->
        <div class="info-section contact-section" v-if="item.contact">
          <h3 class="section-title">联系方式</h3>
          <p class="info-text contact-text">{{ item.contact }}</p>
        </div>

        <!-- 认领按钮（非本人、物品活跃时） -->
        <div class="claim-section" v-if="canClaim">
          <div class="claim-card">
            <el-icon :size="22"><Promotion /></el-icon>
            <span>这是您要找的物品吗？</span>
            <el-button type="success" size="large" @click="handleClaim" :loading="claiming">
              申请认领
            </el-button>
          </div>
        </div>

        <!-- 确认认领区域（本人且有认领通知） -->
        <div class="claim-section" v-if="canEdit && hasClaimNotification">
          <div class="claim-card claim-pending">
            <el-icon :size="22"><Bell /></el-icon>
            <span>有人申请认领该物品</span>
            <div class="claim-actions">
              <el-button type="success" size="default" @click="handleConfirmClaim" :loading="confirming">
                确认认领
              </el-button>
              <el-button type="danger" size="default" plain @click="handleRejectClaim" :loading="confirming">
                拒绝
              </el-button>
            </div>
          </div>
        </div>

        <!-- 操作按钮 -->
        <div class="action-bar" v-if="canEdit">
          <el-button type="primary" @click="editItem" size="large">
            <el-icon><Edit /></el-icon>编辑物品
          </el-button>
          <el-button type="danger" @click="handleDelete" size="large" plain>
            <el-icon><Delete /></el-icon>删除
          </el-button>
        </div>
      </div>
    </div>

    <!-- 加载中 / 不存在 -->
    <div v-else-if="notFound" style="text-align:center;padding:80px 0;">
      <el-empty description="物品不存在或无权查看" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getItem, deleteItem, claimItem, confirmClaim } from '@/api/items'
import { getImageUrl, ITEM_TYPE_MAP, ITEM_STATUS_MAP, REVIEW_STATUS_MAP } from '@/utils/helpers'
import { useAuthStore } from '@/stores/auth'
import { ElMessageBox, ElMessage } from 'element-plus'
import { ArrowLeft, PictureFilled, WarningFilled, Edit, Delete, Promotion, Bell } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const item = ref(null)
const notFound = ref(false)
const claiming = ref(false)
const confirming = ref(false)
const hasClaimNotification = ref(false)

const canEdit = computed(() => {
  if (!item.value) return false
  return authStore.isAdmin || item.value.user_id === authStore.user?.id
})

const canClaim = computed(() => {
  if (!item.value) return false
  return !canEdit.value
    && item.value.status === 'active'
    && item.value.review_status === 'approved'
})

const loadItem = async () => {
  try {
    const res = await getItem(route.params.id)
    if (res.item) {
      item.value = res.item
    } else {
      notFound.value = true
    }
  } catch {
    notFound.value = true
  }
}

const handleDelete = async () => {
  try {
    await ElMessageBox.confirm('确定要删除这件物品吗？此操作不可恢复。', '确认删除', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await deleteItem(route.params.id)
    ElMessage.success('已删除')
    router.push('/items')
  } catch {
    // 用户取消
  }
}

const editItem = () => {
  router.push(`/publish?edit=${route.params.id}`)
}

const handleClaim = async () => {
  try {
    await ElMessageBox.confirm(
      '确认申请认领该物品？系统将通知物品发布者。',
      '申请认领',
      { confirmButtonText: '确认申请', cancelButtonText: '取消', type: 'info' }
    )
    claiming.value = true
    await claimItem(route.params.id)
    ElMessage.success('认领申请已发送，请等待回复')
  } catch {
    // 用户取消
  } finally {
    claiming.value = false
  }
}

const handleConfirmClaim = async () => {
  try {
    await ElMessageBox.confirm(
      '确认后将标记物品为"已认领"，并通知认领人。',
      '确认认领',
      { confirmButtonText: '确认', cancelButtonText: '取消', type: 'warning' }
    )
    confirming.value = true
    // 从通知中提取认领人用户名（简单取法：通知标题中找）
    await confirmClaim(route.params.id, { action: 'confirm', claimer_username: '' })
    ElMessage.success('物品已标记为已认领')
    hasClaimNotification.value = false
    loadItem()
  } catch {
    // 用户取消
  } finally {
    confirming.value = false
  }
}

const handleRejectClaim = async () => {
  confirming.value = true
  try {
    await confirmClaim(route.params.id, { action: 'reject', claimer_username: '' })
    ElMessage.success('已拒绝认领申请')
    hasClaimNotification.value = false
  } catch {
    // 拦截器已处理
  } finally {
    confirming.value = false
  }
}

onMounted(loadItem)
</script>

<style scoped>
.back-row {
  grid-column: 1 / -1;
  margin-bottom: var(--space-3);
}

.back-btn {
  font-size: var(--text-base);
  font-weight: 500;
}

.detail-layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-8);
  align-items: start;
}

/* ---- 图片 ---- */
.detail-hero {
  position: sticky;
  top: 80px;
}

.hero-img-wrapper {
  border-radius: var(--radius-xl);
  overflow: hidden;
  box-shadow: var(--shadow-lg);
  background: var(--neutral-100);
}

.hero-img {
  width: 100%;
  aspect-ratio: 4/3;
  object-fit: cover;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  color: var(--text-muted);
  font-size: var(--text-base);
}

/* ---- 信息 ---- */
.detail-info {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.info-header {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.info-tags {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.item-title {
  font-size: var(--text-4xl);
  font-weight: 700;
  margin: 0;
  color: var(--text-primary);
  line-height: 1.2;
  letter-spacing: -0.02em;
}

/* ---- 信息区块 ---- */
.info-section {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
}

.info-section .section-title {
  margin-bottom: var(--space-4);
}

.info-text {
  font-size: var(--text-md);
  line-height: 1.8;
  color: var(--text-primary);
  margin: 0;
}

.contact-section {
  border-left: 3px solid var(--el-color-primary);
}

.contact-text {
  color: var(--el-color-primary);
  font-weight: 600;
  font-size: var(--text-lg);
}

/* ---- 信息网格 ---- */
.info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-5);
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-label {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.info-value {
  font-size: var(--text-md);
  color: var(--text-primary);
  font-weight: 500;
}

/* ---- 认领区域 ---- */
.claim-section {
  margin-bottom: var(--space-2);
}

.claim-card {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-5);
  background: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-5);
  border-radius: var(--radius-lg);
  color: var(--el-color-primary);
  font-size: var(--text-base);
  font-weight: 500;
  flex-wrap: wrap;
}

.claim-pending {
  background: #FFF8E1;
  border-color: #FFE082;
  color: #E65100;
}

.claim-actions {
  display: flex;
  gap: var(--space-2);
  margin-left: auto;
}

/* ---- 操作按钮 ---- */
.action-bar {
  display: flex;
  gap: var(--space-3);
  padding-top: var(--space-3);
}

/* ---- 响应式 ---- */
@media (max-width: 768px) {
  .detail-layout {
    grid-template-columns: 1fr;
    gap: var(--space-5);
  }
  .detail-hero {
    position: static;
  }
  .item-title {
    font-size: var(--text-3xl);
  }
  .info-grid {
    grid-template-columns: 1fr;
  }
}
</style>
