<template>
  <el-tabs v-model="activeTab" class="claims-tabs">
    <!-- 我的申请 -->
    <el-tab-pane label="我的申请" name="mine">
      <div v-if="mineLoading" class="loading-row"><el-skeleton :rows="3" animated /></div>
      <el-empty v-else-if="!mineList.length" description="暂无认领申请" />
      <div v-else class="claim-list">
        <div v-for="c in mineList" :key="c.id" class="claim-card">
          <div class="claim-card-head" @click="goItem(c.item_id)">
            <img v-if="c.image_path" :src="getImageUrl(c.image_path)" class="claim-thumb" />
            <div v-else class="claim-thumb claim-thumb--empty"><el-icon><PictureFilled /></el-icon></div>
            <div class="claim-title-box">
              <span class="claim-item-title">{{ c.title }}</span>
              <span class="claim-item-type">{{ ITEM_TYPE_MAP[c.type]?.label }}物品</span>
            </div>
            <el-tag
              :color="CLAIM_STATUS_MAP[c.status]?.bg"
              :style="{ color: CLAIM_STATUS_MAP[c.status]?.color, border: 'none' }"
            >
              {{ CLAIM_STATUS_MAP[c.status]?.label }}
            </el-tag>
          </div>
          <div class="claim-card-body">
            <p v-if="c.feature_description" class="claim-line">特征描述：{{ c.feature_description }}</p>
            <p v-if="c.claim_reason" class="claim-line">认领说明：{{ c.claim_reason }}</p>
            <p v-if="c.status === 2 && c.review_remark" class="claim-line claim-line--warn">拒绝理由：{{ c.review_remark }}</p>
            <p class="claim-line claim-line--muted">申请时间：{{ c.created_at }}</p>
          </div>
          <div class="claim-card-foot" v-if="c.status === 0">
            <el-button size="small" type="warning" plain @click="handleCancel(c)">撤销申请</el-button>
          </div>
        </div>
      </div>
      <el-pagination
        v-if="mineTotal > pageSize"
        v-model:current-page="minePage"
        :page-size="pageSize"
        :total="mineTotal"
        layout="prev, pager, next"
        class="pagination-wrap"
        @current-change="loadMine"
      />
    </el-tab-pane>

    <!-- 收到的申请 -->
    <el-tab-pane label="收到的申请" name="received">
      <div v-if="receivedLoading" class="loading-row"><el-skeleton :rows="3" animated /></div>
      <el-empty v-else-if="!receivedList.length" description="暂无收到的申请" />
      <div v-else class="claim-list">
        <div v-for="c in receivedList" :key="c.id" class="claim-card">
          <div class="claim-card-head" @click="goItem(c.item_id)">
            <img v-if="c.image_path" :src="getImageUrl(c.image_path)" class="claim-thumb" />
            <div v-else class="claim-thumb claim-thumb--empty"><el-icon><PictureFilled /></el-icon></div>
            <div class="claim-title-box">
              <span class="claim-item-title">{{ c.title }}</span>
              <span class="claim-item-type">申请人：{{ c.claimer_username }}</span>
            </div>
            <el-tag
              :color="CLAIM_STATUS_MAP[c.status]?.bg"
              :style="{ color: CLAIM_STATUS_MAP[c.status]?.color, border: 'none' }"
            >
              {{ CLAIM_STATUS_MAP[c.status]?.label }}
            </el-tag>
          </div>
          <div class="claim-card-body">
            <p v-if="c.feature_description" class="claim-line">特征描述：{{ c.feature_description }}</p>
            <p v-if="c.claim_reason" class="claim-line">认领说明：{{ c.claim_reason }}</p>
            <p v-if="c.contact_phone" class="claim-line">申请人电话：{{ c.contact_phone }}</p>
            <p v-if="c.proof_image" class="claim-line">
              证明图片：
              <el-image :src="getImageUrl(c.proof_image)" class="proof-img" fit="cover" :preview-src-list="[getImageUrl(c.proof_image)]" preview-teleported />
            </p>
            <p class="claim-line claim-line--muted">申请时间：{{ c.created_at }}</p>
          </div>
          <div class="claim-card-foot" v-if="c.status === 0">
            <el-button size="small" type="success" @click="handleApprove(c)">同意</el-button>
            <el-button size="small" type="danger" plain @click="handleReject(c)">拒绝</el-button>
          </div>
          <div class="claim-card-foot" v-else-if="c.status === 1">
            <el-button size="small" type="primary" @click="handleComplete(c)">确认{{ c.type === 'lost' ? '已找回' : '已归还' }}</el-button>
          </div>
        </div>
      </div>
      <el-pagination
        v-if="receivedTotal > pageSize"
        v-model:current-page="receivedPage"
        :page-size="pageSize"
        :total="receivedTotal"
        layout="prev, pager, next"
        class="pagination-wrap"
        @current-change="loadReceived"
      />
    </el-tab-pane>
  </el-tabs>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { myClaims, receivedClaims, approveClaim, rejectClaim, completeClaim, cancelClaim } from '@/api/claims'
import { getImageUrl, ITEM_TYPE_MAP, CLAIM_STATUS_MAP } from '@/utils/helpers'
import { ElMessage, ElMessageBox } from 'element-plus'
import { PictureFilled } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const activeTab = ref(route.query.tab === 'received' ? 'received' : 'mine')

const mineList = ref([])
const mineTotal = ref(0)
const minePage = ref(1)
const mineLoading = ref(false)

const receivedList = ref([])
const receivedTotal = ref(0)
const receivedPage = ref(1)
const receivedLoading = ref(false)

const pageSize = 10

const goItem = (id) => router.push(`/items/${id}`)

const loadMine = async () => {
  mineLoading.value = true
  try {
    const res = await myClaims({ page: minePage.value, size: pageSize })
    mineList.value = res.claims || []
    mineTotal.value = res.total || 0
  } catch (e) {
    console.error('加载我的申请失败:', e)
  } finally {
    mineLoading.value = false
  }
}

const loadReceived = async () => {
  receivedLoading.value = true
  try {
    const res = await receivedClaims({ page: receivedPage.value, size: pageSize })
    receivedList.value = res.claims || []
    receivedTotal.value = res.total || 0
  } catch (e) {
    console.error('加载收到的申请失败:', e)
  } finally {
    receivedLoading.value = false
  }
}

const handleCancel = async (c) => {
  try {
    await ElMessageBox.confirm('确定撤销该申请吗？撤销后可重新申请。', '撤销申请', {
      confirmButtonText: '撤销', cancelButtonText: '取消', type: 'warning'
    })
  } catch { return }
  try {
    await cancelClaim(c.id)
    ElMessage.success('申请已撤销')
    loadMine()
  } catch (e) { console.error('撤销失败:', e) }
}

const handleApprove = async (c) => {
  try {
    await ElMessageBox.confirm(
      '同意该申请后，该物品的其他待审核申请将自动拒绝，物品进入「认领中」状态。',
      '同意申请',
      { confirmButtonText: '同意', cancelButtonText: '取消', type: 'success' }
    )
  } catch { return }
  try {
    await approveClaim(c.id)
    ElMessage.success('已同意，物品进入认领中')
    loadReceived()
  } catch (e) { console.error('同意失败:', e) }
}

const handleReject = async (c) => {
  let remark = ''
  try {
    const { value } = await ElMessageBox.prompt('请填写拒绝理由（必填，将通知申请人）', '拒绝申请', {
      confirmButtonText: '拒绝', cancelButtonText: '取消',
      inputValidator: (v) => (v && v.trim() ? true : '拒绝理由不能为空')
    })
    remark = value.trim()
  } catch { return }
  try {
    await rejectClaim(c.id, remark)
    ElMessage.success('已拒绝该申请')
    loadReceived()
  } catch (e) { console.error('拒绝失败:', e) }
}

const handleComplete = async (c) => {
  const label = c.type === 'lost' ? '已找回' : '已归还'
  try {
    await ElMessageBox.confirm(
      `确认完成交接？物品将标记为「${label}」并从列表移除。`,
      `确认${label}`,
      { confirmButtonText: '确认', cancelButtonText: '取消', type: 'success' }
    )
  } catch { return }
  try {
    await completeClaim(c.id)
    ElMessage.success(`物品已标记为${label}`)
    loadReceived()
  } catch (e) { console.error('确认失败:', e) }
}

onMounted(() => {
  loadMine()
  loadReceived()
})
</script>

<style scoped>
.claims-tabs { background: transparent; }

.loading-row { padding: var(--space-6); }

.claim-list { display: flex; flex-direction: column; gap: var(--space-4); }

.claim-card {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-xs);
}

.claim-card-head {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4);
  cursor: pointer;
  transition: background var(--transition-fast);
}
.claim-card-head:hover { background: var(--neutral-50); }

.claim-thumb {
  width: 56px;
  height: 56px;
  border-radius: var(--radius-md);
  object-fit: cover;
  flex-shrink: 0;
  border: 1px solid var(--border-light);
}
.claim-thumb--empty {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  background: var(--neutral-100);
}

.claim-title-box { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.claim-item-title { font-weight: 600; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.claim-item-type { font-size: var(--text-xs); color: var(--text-tertiary); }

.claim-card-body { padding: 0 var(--space-4) var(--space-4); }
.claim-line { margin: 0 0 var(--space-1); font-size: var(--text-sm); color: var(--text-secondary); line-height: 1.6; }
.claim-line--muted { color: var(--text-muted); font-size: var(--text-xs); }
.claim-line--warn { color: #E65100; }

.proof-img { width: 72px; height: 72px; border-radius: var(--radius-md); vertical-align: middle; }

.claim-card-foot {
  display: flex;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  border-top: 1px solid var(--border-light);
  justify-content: flex-end;
  background: var(--neutral-50);
}

.pagination-wrap { display: flex; justify-content: center; margin-top: var(--space-6); }
</style>
