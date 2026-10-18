<template>
  <div class="page-container">
    <!-- 返回按钮 -->
    <div class="back-row">
      <el-button :icon="ArrowLeft" @click="$router.back()" text>返回</el-button>
    </div>

    <div v-if="item" class="detail-layout">
      <!-- 左栏：图片 + 缩略图 -->
      <div class="detail-left">
        <div class="img-card">
          <el-image
            v-if="images.length"
            :src="getImageUrl(images[activeImg])"
            :alt="item.title"
            class="hero-img"
            fit="cover"
            :preview-src-list="previewList"
            :initial-index="activeImg"
            preview-teleported
          />
          <div v-else class="img-placeholder">
            <el-icon :size="48"><PictureFilled /></el-icon>
            <span>暂无图片</span>
          </div>
          <!-- 类型徽章（左上） -->
          <span
            class="type-badge"
            :style="{ background: ITEM_TYPE_MAP[item.type]?.bg, color: ITEM_TYPE_MAP[item.type]?.color }"
          >
            {{ ITEM_TYPE_MAP[item.type]?.label }}
          </span>
          <!-- 图片数量角标（右上，参照参考稿的「N 条图片」胶囊） -->
          <span v-if="images.length" class="img-count-badge">{{ images.length }} 条图片</span>
        </div>
        <!-- 缩略图 -->
        <div v-if="images.length > 1" class="thumb-row">
          <div
            v-for="(img, i) in images"
            :key="img"
            class="thumb"
            :class="{ 'thumb--active': i === activeImg }"
            @click="activeImg = i"
          >
            <img :src="getImageUrl(img)" :alt="`图${i + 1}`" loading="lazy" />
            <span v-if="i === 0" class="cover-tag">封面</span>
          </div>
        </div>
        <!-- 认领/归还入口（图片下方） -->
        <!-- 认领状态提示（已有申请时） -->
        <div class="claim-section" v-if="canClaim && myClaim && [0, 1, 2, 3, 4].includes(myClaim.status)">
          <div class="claim-card claim-card--status">
            <div class="claim-body">
              <span class="claim-text">
                您的{{ actionWord }}申请状态：{{ CLAIM_STATUS_MAP[myClaim.status]?.label }}
              </span>
              <span class="claim-hint" v-if="myClaim.status === 2 && myClaim.review_remark">
                拒绝理由：{{ myClaim.review_remark }}
              </span>
              <span class="claim-hint" v-else-if="myClaim.status === 0">请耐心等待发布者处理</span>
              <span class="claim-hint" v-else-if="myClaim.status === 1">请查看右侧联系方式，尽快与发布者完成交接</span>
            </div>
            <el-button
              v-if="myClaim.status === 0"
              type="warning"
              plain
              @click="handleCancelClaim"
              :loading="cancelling"
            >撤销申请</el-button>
          </div>
        </div>

        <!-- 认领/归还按钮（非本人、物品活跃、无待处理申请时） -->
        <div class="claim-section" v-if="canClaim && !myClaim">
          <div class="claim-card">
            <div class="claim-icon">
              <el-icon :size="20"><Promotion /></el-icon>
            </div>
            <div class="claim-body">
              <span class="claim-text">{{ item.type === 'lost' ? '这是您捡到的物品吗？' : '这是您丢失的物品吗？' }}</span>
              <span class="claim-hint">填写物品特征描述可加快发布者核验，防止冒领</span>
            </div>
            <el-button type="success" size="large" @click="openClaimDialog" class="claim-btn">
              {{ item.type === 'lost' ? '我要归还' : '我要认领' }}
            </el-button>
          </div>
        </div>

        <!-- 发布者视角：收到的申请 + 自标记 -->
        <div class="claim-section" v-if="canEdit && (item.status === 'active' || item.status === 'claiming')">
          <div class="claim-card" :class="{ 'claim-card--pending': hasClaimNotification }">
            <div class="claim-icon">
              <el-icon :size="20"><Bell /></el-icon>
            </div>
            <div class="claim-body">
              <span class="claim-text">
                {{ hasClaimNotification ? `有用户申请处理该物品` : (item.type === 'lost' ? '物品已找回？' : '物品已归还？') }}
              </span>
              <span class="claim-hint" v-if="hasClaimNotification">点击「处理申请」同意或拒绝（同意后其他待审核申请将自动拒绝）</span>
              <span class="claim-hint" v-else>确认后物品将从列表移除，移入历史记录</span>
            </div>
            <div class="claim-actions">
              <el-button v-if="hasClaimNotification" type="primary" size="large" @click="goToReceived">
                处理申请
              </el-button>
              <el-button
                type="success"
                size="large"
                @click="handleMarkClaimed"
                :loading="marking"
              >
                {{ item.type === 'lost' ? '标记为已找回' : '标记为已归还' }}
              </el-button>
            </div>
          </div>
        </div>

      </div>

      <!-- 右栏：标题 / 信息 -->
      <div class="detail-right">
        <!-- 标题 -->
        <div class="title-row">
          <h1 class="item-title">{{ item.title }}</h1>
        </div>

        <!-- 驳回理由 -->
        <div v-if="item.review_status === 'rejected' && item.reject_reason" class="reject-box">
          <el-icon :size="18"><WarningFilled /></el-icon>
          <span><strong>驳回理由：</strong>{{ item.reject_reason }}</span>
        </div>

        <!-- 信息区：状态标签 / 基本信息 / 详细描述 / 联系方式 —— 同一张卡片，用分隔线分区 -->
        <div class="info-card">
          <!-- 状态标签（卡片顶部） -->
          <div class="status-tags">
            <span class="status-tag" :style="{ background: ITEM_STATUS_MAP[item.status]?.bg, color: ITEM_STATUS_MAP[item.status]?.color }">
              {{ ITEM_STATUS_MAP[item.status]?.label }}
            </span>
            <span v-if="item.review_status" class="status-tag" :style="{ background: REVIEW_STATUS_MAP[item.review_status]?.bg, color: REVIEW_STATUS_MAP[item.review_status]?.color }">
              审核: {{ REVIEW_STATUS_MAP[item.review_status]?.label }}
            </span>
          </div>
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

          <!-- 详细描述 -->
          <section class="info-block" v-if="item.description">
            <h3 class="card-section-title">详细描述</h3>
            <p class="desc-text">{{ item.description }}</p>
          </section>

          <!-- 联系方式（未通过申请时脱敏展示） -->
          <section class="info-block" v-if="item.contact && !ownerContact">
            <h3 class="card-section-title">联系方式</h3>
            <div class="contact-box">
              <p class="contact-text">{{ item.contact }}</p>
              <span v-if="item.contact_masked" class="contact-hint">为保护隐私已脱敏，认领申请通过后可见完整号码</span>
            </div>
          </section>

          <!-- v3.6.0: 认领通过后展示发布者完整联系方式 -->
          <section class="info-block" v-if="ownerContact">
            <h3 class="card-section-title">发布者联系方式（已通过申请）</h3>
            <div class="contact-box">
              <p class="contact-text">{{ ownerContact }}</p>
            </div>
          </section>
        </div>

        <!-- 编辑/删除（v3.6.1：已审核通过的物品对发布者只读，只能删除） -->
        <div class="action-bar" v-if="canEdit">
          <el-button v-if="canModify" type="primary" @click="editItem" size="large">
            <el-icon><Edit /></el-icon>编辑物品
          </el-button>
          <span v-else class="edit-locked-hint">该物品已审核通过，无法修改；如需更正请删除后重新发布</span>
          <el-button type="danger" @click="handleDelete" size="large" plain>
            <el-icon><Delete /></el-icon>删除
          </el-button>
        </div>
      </div>
    </div>

    <!-- 相似推荐（v3.6.0，异步加载） -->
    <div v-if="item" class="similar-section">
      <h2 class="section-title">相似推荐</h2>
      <p class="section-hint" v-if="similarLoading">正在进行图片智能匹配，推荐结果稍后呈现……</p>
      <div v-else-if="similarItems.length" class="similar-grid">
        <div
          v-for="s in similarItems"
          :key="s.id"
          class="similar-card"
          @click="router.push(`/items/${s.id}`)"
        >
          <img v-if="s.image_path" :src="getImageUrl(s.image_path)" :alt="s.title" loading="lazy" />
          <div class="similar-card-body">
            <div class="similar-title">{{ s.title }}</div>
            <div class="similar-meta">
              <span v-if="s.category">{{ s.category }}</span>
              <span v-if="s.location">{{ s.location }}</span>
            </div>
            <div class="similar-score">
              <el-tag :color="evidenceColor(s.level)" effect="plain" size="small" style="border:none;">
                {{ EVIDENCE_LEVEL_MAP[s.level]?.label || '' }}
              </el-tag>
              <span class="score-num">{{ (s.similarity * 100).toFixed(1) }}%</span>
            </div>
          </div>
        </div>
      </div>
      <el-empty v-else-if="!similarLoading && similarLoaded" description="暂无相似物品" :image-size="64" />
    </div>

    <!-- 留言区（v3.6.0） -->
    <div v-if="item" class="comments-section">
      <h2 class="section-title">在线留言（{{ commentTree.length }}）</h2>

      <!-- 发表留言 -->
      <div class="comment-composer" v-if="authStore.token">
        <el-input
          v-model="commentDraft"
          type="textarea"
          :rows="2"
          maxlength="500"
          show-word-limit
          placeholder="写下您的留言（如：我在附近见过这个物品）"
        />
        <el-button type="primary" @click="submitComment()" :loading="commentSubmitting">发表留言</el-button>
      </div>
      <div class="comment-composer--guest" v-else>
        <el-button text type="primary" @click="router.push('/login')">登录后发表留言</el-button>
      </div>

      <!-- 留言树 -->
      <div v-if="commentTree.length" class="comment-list">
        <div v-for="c in commentTree" :key="c.id" class="comment-item">
          <div class="comment-main">
            <div class="comment-head">
              <span class="comment-user">{{ c.username }}</span>
              <span class="comment-time">{{ c.created_at }}</span>
            </div>
            <p class="comment-content">{{ c.content }}</p>
            <div class="comment-actions">
              <el-button text size="small" v-if="authStore.token" @click="toggleReply(c)">回复</el-button>
              <el-button text size="small" type="danger" v-if="canDeleteComment(c)" @click="handleDeleteComment(c)">删除</el-button>
              <el-button text size="small" type="warning" v-if="authStore.isAdmin" @click="handleToggleHide(c)">隐藏</el-button>
            </div>
            <!-- 回复输入框 -->
            <div v-if="replyingTo === c.id" class="reply-box">
              <el-input
                v-model="replyDraft"
                type="textarea"
                :rows="2"
                maxlength="500"
                :placeholder="`回复 @${c.username}`"
              />
              <div class="reply-actions">
                <el-button size="small" @click="replyingTo = null">取消</el-button>
                <el-button size="small" type="primary" @click="submitComment(c)" :loading="commentSubmitting">回复</el-button>
              </div>
            </div>
          </div>
          <!-- 楼中楼子回复 -->
          <div v-if="c.children && c.children.length" class="comment-children">
            <div v-for="ch in c.children" :key="ch.id" class="comment-item comment-item--child">
              <div class="comment-head">
                <span class="comment-user">{{ ch.username }}</span>
                <span class="comment-time">{{ ch.created_at }}</span>
              </div>
              <p class="comment-content">{{ ch.content }}</p>
              <div class="comment-actions">
                <el-button text size="small" type="danger" v-if="canDeleteComment(ch)" @click="handleDeleteComment(ch)">删除</el-button>
                <el-button text size="small" type="warning" v-if="authStore.isAdmin" @click="handleToggleHide(ch)">隐藏</el-button>
              </div>
            </div>
          </div>
        </div>
      </div>
      <el-empty v-else description="还没有留言，来抢沙发" :image-size="64" />
    </div>

    <!-- 举报入口（v3.6.0） -->
    <div v-if="item" class="report-row">
      <el-button text type="danger" @click="reportVisible = true">
        <el-icon><Warning /></el-icon>举报此信息
      </el-button>
    </div>

    <!-- 不存在 -->
    <div v-else-if="notFound" style="text-align:center;padding:80px 0;">
      <el-empty description="物品不存在" />
    </div>

    <!-- 认领申请对话框（v3.6.0：特征描述 + 证明图） -->
    <el-dialog v-model="claimVisible" :title="`申请${actionWord}`" width="480px">
      <el-form label-position="top">
        <el-form-item label="认领说明">
          <el-input v-model="claimForm.claim_reason" type="textarea" :rows="2" maxlength="500" show-word-limit placeholder="选填：说明情况" />
        </el-form-item>
        <el-form-item label="物品特征描述（防冒领核验依据）" required>
          <el-input v-model="claimForm.feature_description" maxlength="200" show-word-limit placeholder="如：黑色、左角有划痕、内有某证件" />
        </el-form-item>
        <el-form-item label="证明图片（选填，限 1 张）">
          <el-upload
            :auto-upload="false"
            :limit="1"
            list-type="picture-card"
            accept="image/*"
            :on-change="onProofChange"
            :on-remove="onProofRemove"
            v-model:file-list="proofFileList"
          >
            <el-icon><Plus /></el-icon>
          </el-upload>
        </el-form-item>
        <el-form-item label="联系电话">
          <el-input v-model="claimForm.contact_phone" maxlength="20" placeholder="选填：默认使用您资料中的电话" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="claimVisible = false">取消</el-button>
        <el-button type="primary" @click="submitClaim" :loading="claimSubmitting">提交申请</el-button>
      </template>
    </el-dialog>

    <!-- 举报对话框 -->
    <el-dialog v-model="reportVisible" title="举报此信息" width="440px">
      <el-form label-position="top">
        <el-form-item label="举报类型" required>
          <el-select v-model="reportForm.report_type" style="width: 100%">
            <el-option v-for="(v, k) in REPORT_TYPE_MAP" :key="k" :label="v.label" :value="Number(k)" />
          </el-select>
        </el-form-item>
        <el-form-item label="举报原因" required>
          <el-input v-model="reportForm.report_reason" type="textarea" :rows="3" maxlength="500" show-word-limit placeholder="请描述具体情况" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="reportVisible = false">取消</el-button>
        <el-button type="danger" @click="submitReport" :loading="reportSubmitting">提交举报</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getItem, deleteItem, markClaimed, getSimilar } from '@/api/items'
import { getUnreadList } from '@/api/notifications'
import { claimStatus, applyClaim, uploadProof, cancelClaim, getClaim } from '@/api/claims'
import { listComments, postComment, deleteComment, adminSetCommentStatus } from '@/api/comments'
import { submitReport as apiSubmitReport } from '@/api/reports'
import {
  getImageUrl, ITEM_TYPE_MAP, ITEM_STATUS_MAP, REVIEW_STATUS_MAP,
  CLAIM_STATUS_MAP, REPORT_TYPE_MAP, EVIDENCE_LEVEL_MAP, parseItemImages
} from '@/utils/helpers'
import { useAuthStore } from '@/stores/auth'
import { ElMessageBox, ElMessage } from 'element-plus'
import { ArrowLeft, PictureFilled, WarningFilled, Edit, Delete, Promotion, Bell, Checked, Plus, Warning } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const item = ref(null)
const notFound = ref(false)
const marking = ref(false)
const hasClaimNotification = ref(false)

// ---- 多图画廊 ----
const images = computed(() => parseItemImages(item.value))
const activeImg = ref(0)
const previewList = computed(() => images.value.map((f) => getImageUrl(f)))

const canEdit = computed(() => {
  if (!item.value) return false
  return authStore.isAdmin || item.value.user_id === authStore.user?.id
})

// v3.6.1：审核通过后发布者不可再编辑（管理员不受限），只保留删除
const canModify = computed(() => {
  if (!canEdit.value) return false
  return authStore.isAdmin || item.value?.review_status !== 'approved'
})

const actionWord = computed(() => (item.value?.type === 'lost' ? '归还' : '认领'))

const canClaim = computed(() => {
  if (!item.value) return false
  return !canEdit.value
    && item.value.status === 'active'
    && item.value.review_status === 'approved'
})

// ---- 认领闭环状态 ----
const myClaim = ref(null)
const ownerContact = ref('')
const claimVisible = ref(false)
const claimSubmitting = ref(false)
const cancelling = ref(false)
const proofFileList = ref([])
const claimForm = ref({ claim_reason: '', feature_description: '', contact_phone: '', proof_image: '' })

const loadClaimState = async () => {
  if (!canClaim.value) return
  try {
    const res = await claimStatus(route.params.id)
    myClaim.value = res.claim || null
    if (myClaim.value && [1, 3].includes(myClaim.value.status)) {
      const detail = await getClaim(myClaim.value.id)
      ownerContact.value = detail.claim?.owner_contact || ''
    }
  } catch {
    // 静默失败：不影响详情浏览
  }
}

const openClaimDialog = () => {
  claimForm.value = {
    claim_reason: '',
    feature_description: '',
    contact_phone: authStore.user?.phone || '',
    proof_image: ''
  }
  proofFileList.value = []
  claimVisible.value = true
}

const onProofChange = (file) => {
  claimForm.value.proof_image = file?.name || ''
}
const onProofRemove = () => {
  claimForm.value.proof_image = ''
}

const submitClaim = async () => {
  if (!claimForm.value.feature_description.trim()) {
    ElMessage.warning('请填写物品特征描述（防冒领核验依据）')
    return
  }
  claimSubmitting.value = true
  try {
    // 先上传证明图（若有）
    const rawFile = proofFileList.value[0]?.raw
    if (rawFile) {
      const up = await uploadProof(rawFile)
      claimForm.value.proof_image = up.path
    }
    await applyClaim({
      item_id: Number(route.params.id),
      claim_reason: claimForm.value.claim_reason,
      feature_description: claimForm.value.feature_description,
      contact_phone: claimForm.value.contact_phone,
      proof_image: claimForm.value.proof_image || null
    })
    ElMessage.success(`${actionWord.value}申请已发送，请等待发布者处理`)
    claimVisible.value = false
    await loadClaimState()
  } catch (e) {
    console.error('认领申请失败:', e)
  } finally {
    claimSubmitting.value = false
  }
}

const handleCancelClaim = async () => {
  try {
    await ElMessageBox.confirm('确定撤销该申请吗？撤销后可重新申请。', '撤销申请', {
      confirmButtonText: '撤销', cancelButtonText: '取消', type: 'warning'
    })
  } catch { return }
  cancelling.value = true
  try {
    await cancelClaim(myClaim.value.id)
    ElMessage.success('申请已撤销')
    myClaim.value = null
  } catch (e) {
    console.error('撤销失败:', e)
  } finally {
    cancelling.value = false
  }
}

// ---- 相似推荐 ----
const similarItems = ref([])
const similarLoading = ref(false)
const similarLoaded = ref(false)
const loadSimilar = async () => {
  similarLoading.value = true
  try {
    const res = await getSimilar(route.params.id, { limit: 6 })
    similarItems.value = res.items || []
  } catch {
    similarItems.value = []
  } finally {
    similarLoading.value = false
    similarLoaded.value = true
  }
}
const evidenceColor = (level) => EVIDENCE_LEVEL_MAP[level]?.color || '#9E9E9E'

// ---- 留言 ----
const commentFlat = ref([])
const commentDraft = ref('')
const commentSubmitting = ref(false)
const replyingTo = ref(null)
const replyDraft = ref('')

const commentTree = computed(() => {
  const tops = commentFlat.value.filter((c) => !c.parent_id)
  return tops.map((t) => ({
    ...t,
    children: commentFlat.value.filter((c) => c.parent_id === t.id)
  }))
})

const loadComments = async () => {
  try {
    const res = await listComments(route.params.id)
    commentFlat.value = res.comments || []
  } catch {
    commentFlat.value = []
  }
}

const submitComment = async (parent = null) => {
  const content = parent ? replyDraft.value.trim() : commentDraft.value.trim()
  if (!content) {
    ElMessage.warning('留言内容不能为空')
    return
  }
  commentSubmitting.value = true
  try {
    await postComment({ item_id: Number(route.params.id), content, parent_id: parent?.id || null })
    if (parent) {
      replyDraft.value = ''
      replyingTo.value = null
    } else {
      commentDraft.value = ''
    }
    await loadComments()
  } catch (e) {
    console.error('留言失败:', e)
  } finally {
    commentSubmitting.value = false
  }
}

const toggleReply = (c) => {
  replyingTo.value = replyingTo.value === c.id ? null : c.id
  replyDraft.value = ''
}

const canDeleteComment = (c) => c.is_mine || authStore.isAdmin

const handleDeleteComment = async (c) => {
  try {
    await ElMessageBox.confirm('确定删除该留言吗？其下回复将一并删除。', '删除留言', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning'
    })
  } catch { return }
  try {
    await deleteComment(c.id)
    ElMessage.success('已删除')
    await loadComments()
  } catch (e) {
    console.error('删除留言失败:', e)
  }
}

const handleToggleHide = async (c) => {
  try {
    await adminSetCommentStatus(c.id, 0)
    ElMessage.success('已隐藏')
    await loadComments()
  } catch (e) {
    console.error('隐藏失败:', e)
  }
}

// ---- 举报 ----
const reportVisible = ref(false)
const reportSubmitting = ref(false)
const reportForm = ref({ report_type: 1, report_reason: '' })

const submitReport = async () => {
  if (!reportForm.value.report_reason.trim()) {
    ElMessage.warning('请填写举报原因')
    return
  }
  reportSubmitting.value = true
  try {
    await apiSubmitReport({
      item_id: Number(route.params.id),
      report_type: reportForm.value.report_type,
      report_reason: reportForm.value.report_reason
    })
    ElMessage.success('举报已提交，管理员将尽快处理')
    reportVisible.value = false
  } catch (e) {
    console.error('举报失败:', e)
  } finally {
    reportSubmitting.value = false
  }
}

// ---- 原有逻辑 ----
const loadItem = async () => {
  try {
    const res = await getItem(route.params.id)
    if (res.item) {
      item.value = res.item
      activeImg.value = 0
      loadClaimState()
      loadSimilar()
      loadComments()
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
      (n.link === `/claims/received` || n.link === `/items/${route.params.id}`) &&
      (n.title.includes('认领') || n.title.includes('归还'))
    )
    if (claimNotif) {
      hasClaimNotification.value = true
    }
  } catch {
    // 静默失败
  }
}

const goToReceived = () => {
  router.push({ path: '/claims', query: { tab: 'received' } })
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

// v3.3: 发布者自标记（替代原确认/拒绝）
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
  /* 左图 + 右侧信息合并成一张白色面板；图片有宽度上限，不再随屏幕无限放大 */
  grid-template-columns: minmax(280px, 460px) minmax(0, 1fr);
  gap: var(--space-6);
  align-items: start;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
}

/* ========================================
   左栏：图片 + 缩略图（在面板内，不再自成卡片）
   ======================================== */
.detail-left {
  /* 认领入口在右栏，左栏不会变得很高，这里不需要 sticky */
  align-self: start;
}

.img-card {
  position: relative;
  border-radius: var(--radius-lg);
  overflow: hidden;
  background: var(--neutral-100);
}

.hero-img {
  width: 100%;
  aspect-ratio: 4 / 3;
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

/* 类型徽章：尺寸与大厅卡片保持一致（theme.css 里的 .type-badge：3px 12px / 12px / 600）
   必须显式 right:auto，否则会继承全局规则的 right:12px，left+right 同时生效会把徽章拉满整条 */
.type-badge {
  position: absolute;
  top: var(--space-3);
  left: var(--space-3);
  right: auto;
  padding: 3px 12px;
  border-radius: var(--radius-full);
  font-size: var(--text-sm);
  font-weight: 600;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  box-shadow: var(--shadow-sm);
  letter-spacing: 0.02em;
}

/* 右上角「N 条图片」胶囊（参照参考稿写法） */
.img-count-badge {
  position: absolute;
  top: var(--space-3);
  right: var(--space-3);
  padding: 3px 12px;
  border-radius: var(--radius-full);
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  font-size: var(--text-xs);
  font-weight: 500;
  letter-spacing: 0.02em;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}

/* 缩略图行 */
.thumb-row {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-3);
  flex-wrap: wrap;
}

.thumb {
  width: 72px;
  height: 72px;
  border-radius: var(--radius-md);
  overflow: hidden;
  cursor: pointer;
  border: 2px solid transparent;
  position: relative;
  opacity: 0.75;
  transition: all 0.2s ease;
}

.thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumb--active {
  border-color: var(--el-color-primary);
  opacity: 1;
}

.cover-tag {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
  font-size: 10px;
  text-align: center;
  padding: 1px 0;
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

.status-tag {
  padding: 3px 12px;
  border-radius: var(--radius-full);
  font-size: var(--text-sm);
  font-weight: 600;
}

/* 状态标签并入信息卡顶部，用分隔线与下方信息行区分 */
.info-card > .status-tags {
  padding-bottom: var(--space-3);
  margin-bottom: var(--space-3);
  border-bottom: 1px solid var(--border-light);
}

/* ---- 信息区（在面板内，不再套一层卡片） ---- */
.info-card {
  background: transparent;
  border: none;
  border-radius: 0;
  padding: 0;
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

/* ---- 卡片内分区（基本信息 / 详细描述 / 联系方式 合并在同一张卡片里） ---- */
.info-block {
  margin-top: var(--space-4);
  padding-top: var(--space-4);
  border-top: 1px solid var(--border-light);
}

/* 联系方式：卡片内的高亮小色块，替代原来独立的卡片 */
.contact-box {
  padding: var(--space-3) var(--space-4);
  background: var(--el-color-primary-light-9);
  border-left: 3px solid var(--el-color-primary);
  border-radius: var(--radius-md);
}

.contact-text {
  font-size: var(--text-lg);
  color: var(--el-color-primary);
  font-weight: 600;
  margin: 0;
}

.contact-hint {
  display: block;
  margin-top: 4px;
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

/* ---- 驳回提示 ---- */
.reject-box {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  background: #FFEBEE;
  border: 1px solid #FFCDD2;
  border-radius: var(--radius-md);
  color: #C62828;
  font-size: var(--text-sm);
}

/* ---- 认领卡片（图片下方） ---- */
.claim-section {
  /* wrapper for spacing */
}

/* 左栏：认领区与图片/缩略图之间留白 */
.detail-left .claim-section {
  margin-top: var(--space-4);
}

/* 左栏只有 460px 宽：按钮换到单独一行占满宽度，避免文案被挤成多行 */
.detail-left .claim-card {
  padding: var(--space-4);
}

.detail-left .claim-btn,
.detail-left .claim-actions {
  flex: 1 1 100%;
  margin-top: var(--space-2);
}

.detail-left .claim-btn {
  width: 100%;
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

.claim-card--status {
  background: #F5F7FA;
  border-color: var(--border-light);
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

.claim-card--pending .claim-text {
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

.edit-locked-hint {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  align-items: center;
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  line-height: 1.6;
}

/* ========================================
   全宽区块：相似推荐 / 留言 / 举报
   ======================================== */
.similar-section,
.comments-section {
  margin-top: var(--space-10);
}

.section-title {
  font-size: var(--text-2xl);
  font-weight: 700;
  margin: 0 0 var(--space-4);
  color: var(--text-primary);
}

.section-hint {
  color: var(--text-tertiary);
  font-size: var(--text-sm);
}

.similar-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: var(--space-4);
}

.similar-card {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  overflow: hidden;
  cursor: pointer;
  transition: all 0.2s ease;
}

.similar-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

.similar-card img {
  width: 100%;
  aspect-ratio: 4 / 3;
  object-fit: cover;
  display: block;
}

.similar-card-body {
  padding: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.similar-title {
  font-weight: 600;
  font-size: var(--text-base);
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.similar-meta {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  display: flex;
  gap: var(--space-2);
}

.similar-score {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.score-num {
  font-weight: 700;
  color: var(--el-color-primary);
  font-size: var(--text-sm);
}

/* ---- 留言 ---- */
.comment-composer {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin-bottom: var(--space-6);
}

.comment-composer--guest {
  margin-bottom: var(--space-6);
  color: var(--text-tertiary);
  font-size: var(--text-sm);
}

.comment-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.comment-item {
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  background: var(--bg-card);
  overflow: hidden;
}

.comment-main {
  padding: var(--space-4);
}

.comment-head {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}

.comment-user {
  font-weight: 600;
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.comment-time {
  color: var(--text-tertiary);
  font-size: var(--text-xs);
}

.comment-content {
  margin: 0;
  color: var(--text-primary);
  font-size: var(--text-base);
  line-height: 1.7;
  white-space: pre-wrap;
}

.comment-actions {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-2);
}

.reply-box {
  margin-top: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.reply-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
}

.comment-children {
  border-top: 1px dashed var(--border-light);
  background: var(--neutral-50);
}

.comment-item--child {
  border: none;
  border-radius: 0;
  background: transparent;
  padding: var(--space-3) var(--space-4) var(--space-3) var(--space-8);
  border-bottom: 1px solid var(--border-light);
}

.comment-item--child:last-child {
  border-bottom: none;
}

/* ---- 举报行 ---- */
.report-row {
  margin-top: var(--space-8);
  text-align: right;
}

/* ========================================
   响应式：768px 以下单栏
   ======================================== */
@media (max-width: 768px) {
  .detail-layout {
    grid-template-columns: 1fr;
    gap: var(--space-5);
    padding: var(--space-4);
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
