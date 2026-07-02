<template>
  <div class="page-container">
    <!-- 返回按钮 -->
    <div class="back-row">
      <el-button :icon="ArrowLeft" @click="$router.back()" text>返回</el-button>
    </div>

    <div v-if="item" class="detail-layout">
      <!-- 左栏：图片 -->
      <div class="detail-left">
        <div class="img-card">
          <img
            v-if="item.image_path"
            :src="getImageUrl(item.image_path)"
            :alt="item.title"
            class="hero-img"
            loading="lazy"
          />
          <div v-else class="img-placeholder">
            <el-icon :size="48"><PictureFilled /></el-icon>
            <span>暂无图片</span>
          </div>
          <!-- 类型徽章 -->
          <span
            class="type-badge"
            :style="{ background: ITEM_TYPE_MAP[item.type]?.bg, color: ITEM_TYPE_MAP[item.type]?.color }"
          >
            {{ ITEM_TYPE_MAP[item.type]?.label }}
          </span>
        </div>
      </div>

      <!-- 右栏：信息 -->
      <div class="detail-right">
        <!-- 标题 + 状态标签 -->
        <div class="title-row">
          <h1 class="item-title">{{ item.title }}</h1>
          <div class="status-tags">
            <span class="status-tag" :style="{ background: ITEM_STATUS_MAP[item.status]?.bg, color: ITEM_STATUS_MAP[item.status]?.color }">
              {{ ITEM_STATUS_MAP[item.status]?.label }}
            </span>
            <span v-if="item.review_status" class="status-tag" :style="{ background: REVIEW_STATUS_MAP[item.review_status]?.bg, color: REVIEW_STATUS_MAP[item.review_status]?.color }">
              审核: {{ REVIEW_STATUS_MAP[item.review_status]?.label }}
            </span>
          </div>
        </div>

        <!-- 驳回理由 -->
        <div v-if="item.review_status === 'rejected' && item.reject_reason" class="reject-box">
          <el-icon :size="18"><WarningFilled /></el-icon>
          <span><strong>驳回理由：</strong>{{ item.reject_reason }}</span>
        </div>

        <!-- 基本信息卡片 -->
        <div class="info-card">
          <div class="info-rows">
            <div class="info-row" v-if="item.category">
              <span class="info-label">分类</span>
              <span class="info-value">{{ item.category }}</span>
            </div>
            <div class="info-row" v-if="item.location">
              <span class="info-label">位置</span>
              <span class="info-value">{{ item.location }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">发布时间</span>
              <span class="info-value">{{ item.created_at }}</span>
            </div>
            <div class="info-row" v-if="item.review_time">
              <span class="info-label">审核时间</span>
              <span class="info-value">{{ item.review_time }}</span>
            </div>
          </div>
        </div>

        <!-- 详细描述 -->
        <div class="info-card" v-if="item.description">
          <h3 class="card-section-title">详细描述</h3>
          <p class="desc-text">{{ item.description }}</p>
        </div>

        <!-- 联系方式 -->
        <div class="info-card contact-card" v-if="item.contact">
          <h3 class="card-section-title">联系方式</h3>
          <p class="contact-text">{{ item.contact }}</p>
        </div>

        <!-- 认领/归还按钮（非本人、物品活跃时） -->
        <div class="claim-section" v-if="canClaim">
          <div class="claim-card">
            <div class="claim-icon">
              <el-icon :size="20"><Promotion /></el-icon>
            </div>
            <div class="claim-body">
              <span class="claim-text">{{ item.type === 'lost' ? '这是您捡到的物品吗？' : '这是您丢失的物品吗？' }}</span>
              <span class="claim-hint">点击下方按钮，系统将通知物品发布者</span>
            </div>
            <el-button type="success" size="large" @click="handleClaim" :loading="claiming" class="claim-btn">
              {{ item.type === 'lost' ? '我要归还' : '我要认领' }}
            </el-button>
          </div>
        </div>

        <!-- v3.3: 发布者自标记区域（本人 + 物品活跃 + 有待处理申请时突出提示） -->
        <div class="claim-section" v-if="canEdit && item.status === 'active'">
          <div class="claim-card" :class="{ 'claim-card--pending': hasClaimNotification }">
            <div class="claim-icon">
              <el-icon :size="20"><Checked /></el-icon>
            </div>
            <div class="claim-body">
              <span class="claim-text">
                {{ item.type === 'lost' ? '物品已找回？' : '物品已归还？' }}
              </span>
              <span class="claim-hint" v-if="hasClaimNotification">{{ claimNotificationText }}</span>
              <span class="claim-hint" v-else>确认后物品将从列表移除，移入历史记录</span>
            </div>
            <el-button
              type="success"
              size="large"
              @click="handleMarkClaimed"
              :loading="marking"
              class="claim-btn"
            >
              {{ item.type === 'lost' ? '标记为已找回' : '标记为已归还' }}
            </el-button>
          </div>
        </div>

        <!-- 编辑/删除按钮 -->
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

    <!-- 不存在 -->
    <div v-else-if="notFound" style="text-align:center;padding:80px 0;">
      <el-empty description="物品不存在" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getItem, deleteItem, claimItem, markClaimed } from '@/api/items'
import { getUnreadList } from '@/api/notifications'
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
const claimNotificationText = ref('有人申请处理该物品')
const claimerName = ref('')

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
      // 检查是否有待处理的认领/归还通知
      if (canEdit.value) {
        checkClaimNotifications()
      }
    } else {
      notFound.value = true
    }
  } catch {
    notFound.value = true
  }
}

const checkClaimNotifications = async () => {
  try {
    const res = await getUnreadList()
    const notifs = res.notifications || []
    const claimNotif = notifs.find(n =>
      n.link === `/items/${route.params.id}` &&
      (n.title.includes('认领') || n.title.includes('归还'))
    )
    if (claimNotif) {
      hasClaimNotification.value = true
      claimNotificationText.value = claimNotif.title
      // 从标题中提取申请人用户名
      const match = claimNotif.title.match(/用户 '(.+?)'/)
      if (match) claimerName.value = match[1]
    }
  } catch {
    // 静默失败
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
  // v3.3: 根据物品类型区分文案 — lost→归还, found→认领
  const actionWord = item.value?.type === 'lost' ? '归还' : '认领'
  try {
    await ElMessageBox.confirm(
      `确认申请${actionWord}该物品？系统将向发布者发送通知（含您的联系方式），请保持电话畅通。`,
      `申请${actionWord}`,
      { confirmButtonText: `确认${actionWord}`, cancelButtonText: '取消', type: 'info' }
    )
  } catch {
    return  // 用户取消
  }

  claiming.value = true
  try {
    await claimItem(route.params.id)
    ElMessage.success(`${actionWord}申请已发送，请等待发布者联系`)
  } catch (e) {
    console.error('认领申请失败:', e)
    // axios 拦截器已显示错误
  } finally {
    claiming.value = false
  }
}

// v3.3: 发布者自标记（替代原确认/拒绝）
const marking = ref(false)
const handleMarkClaimed = async () => {
  const actionLabel = item.value?.type === 'lost' ? '已找回' : '已归还'
  try {
    await ElMessageBox.confirm(
      `确认后将标记为"${actionLabel}"，物品将从列表页移除并移入历史记录。`,
      `确认标记${actionLabel}`,
      { confirmButtonText: '确认', cancelButtonText: '取消', type: 'success' }
    )
  } catch {
    return  // 用户取消
  }

  marking.value = true
  try {
    await markClaimed(route.params.id)
    ElMessage.success(`物品已标记为${actionLabel}`)
    loadItem()
  } catch (e) {
    console.error('标记失败:', e)
    // axios 拦截器已显示错误
  } finally {
    marking.value = false
  }
}

onMounted(loadItem)
</script>

<style scoped>
/* ========================================
   返回按钮（独立于详情网格）
   ======================================== */
.back-row {
  margin-bottom: var(--space-5);
}

/* ========================================
   双栏布局
   ======================================== */
.detail-layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-8);
  align-items: start;
}

/* ========================================
   左栏：图片卡片
   ======================================== */
.detail-left {
  position: sticky;
  top: 80px;
}

.img-card {
  position: relative;
  border-radius: var(--radius-xl);
  overflow: hidden;
  box-shadow: var(--shadow-lg);
  background: var(--neutral-100);
  border: 1px solid var(--border-light);
}

.hero-img {
  width: 100%;
  aspect-ratio: 4 / 3;
  object-fit: cover;
  display: block;
}

.img-placeholder {
  width: 100%;
  aspect-ratio: 4 / 3;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  color: var(--text-muted);
  font-size: var(--text-sm);
}

.type-badge {
  position: absolute;
  top: var(--space-3);
  right: var(--space-3);
  padding: 4px 14px;
  border-radius: var(--radius-full);
  font-size: var(--text-sm);
  font-weight: 700;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  box-shadow: var(--shadow-sm);
  letter-spacing: 0.02em;
}

/* ========================================
   右栏：信息区
   ======================================== */
.detail-right {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

/* ---- 标题行 ---- */
.title-row {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.item-title {
  font-size: var(--text-4xl);
  font-weight: 700;
  margin: 0;
  color: var(--text-primary);
  line-height: 1.2;
  letter-spacing: -0.02em;
}

.status-tags {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}

/* ---- 信息卡片 ---- */
.info-card {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
}

.info-rows {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-2) 0;
}

.info-row + .info-row {
  border-top: 1px solid var(--border-light);
}

.info-label {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
  font-weight: 500;
  letter-spacing: 0.02em;
  flex-shrink: 0;
}

.info-value {
  font-size: var(--text-base);
  color: var(--text-primary);
  font-weight: 500;
  text-align: right;
}

.card-section-title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-tertiary);
  margin: 0 0 var(--space-3);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.desc-text {
  font-size: var(--text-md);
  line-height: 1.8;
  color: var(--text-primary);
  margin: 0;
}

/* 联系方式卡片 */
.contact-card {
  border-left: 3px solid var(--el-color-primary);
}

.contact-text {
  font-size: var(--text-lg);
  color: var(--el-color-primary);
  font-weight: 600;
  margin: 0;
}

/* ---- 认领卡片 ---- */
.claim-section {
  /* wrapper for spacing */
}

.claim-card {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-5);
  background: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-5);
  border-radius: var(--radius-lg);
  flex-wrap: wrap;
}

.claim-card--pending {
  background: #FFF8E1;
  border-color: #FFE082;
}

.claim-icon {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--el-color-primary);
  flex-shrink: 0;
}

.claim-card--pending .claim-icon {
  color: #E65100;
}

.claim-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.claim-text {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--el-color-primary);
}

.claim-text--pending {
  color: #E65100;
}

.claim-hint {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

.claim-btn {
  flex-shrink: 0;
}

.claim-actions {
  display: flex;
  gap: var(--space-2);
  flex-shrink: 0;
}

/* ---- 操作按钮 ---- */
.action-bar {
  display: flex;
  gap: var(--space-3);
  padding-top: var(--space-2);
}

/* ========================================
   响应式：768px 以下单栏
   ======================================== */
@media (max-width: 768px) {
  .detail-layout {
    grid-template-columns: 1fr;
    gap: var(--space-5);
  }

  .detail-left {
    position: static;
  }

  .item-title {
    font-size: var(--text-3xl);
  }
}

/* ========================================
   响应式：480px 以下紧凑
   ======================================== */
@media (max-width: 480px) {
  .item-title {
    font-size: var(--text-2xl);
  }

  .claim-card {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-3);
  }

  .claim-btn {
    width: 100%;
  }

  .claim-actions {
    width: 100%;
  }

  .claim-actions .el-button {
    flex: 1;
  }

  .action-bar {
    flex-direction: column;
  }

  .action-bar .el-button {
    width: 100%;
  }
}
</style>
