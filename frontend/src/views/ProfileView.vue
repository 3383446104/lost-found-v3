<template>
  <div class="page-container">
    <!-- 顶部：大标题 + 副标题 -->
    <div class="page-header">
      <h1 class="page-title">个人中心</h1>
      <p class="page-desc">管理您的账户信息与业务入口</p>
    </div>

    <!-- 业务导航 Tabs（胶囊） -->
    <div class="business-tabs">
      <button v-for="tab in businessTabs" :key="tab.key" class="biz-tab" @click="goBusinessTab(tab.key)">
        <el-icon :size="14"><component :is="tab.icon" /></el-icon>
        <span>{{ tab.label }}</span>
      </button>
    </div>

    <!-- 主体：左右分栏 -->
    <div class="profile-layout">
      <!-- 左侧：头像卡 + 二级菜单 -->
      <aside class="profile-left">
        <div class="card avatar-card">
          <div class="avatar-placeholder">{{ userFirstLetter }}</div>
          <p class="avatar-hint">支持 JPG/PNG，建议 1:1 比例</p>
        </div>

        <div class="card side-menu">
          <button
            class="side-item"
            :class="{ active: activeSection === 'info' }"
            @click="activeSection = 'info'"
          >
            <el-icon :size="16"><User /></el-icon>
            <span>基本信息</span>
          </button>
          <button
            class="side-item"
            :class="{ active: activeSection === 'password' }"
            @click="activeSection = 'password'"
          >
            <el-icon :size="16"><Lock /></el-icon>
            <span>修改密码</span>
          </button>
        </div>
      </aside>

      <!-- 右侧：可编辑表单区 -->
      <div class="profile-right">
        <!-- 基本信息表单 -->
        <section v-show="activeSection === 'info'" class="card form-card">
          <h3 class="section-title">基本信息</h3>
          <el-form ref="infoFormRef" :model="infoForm" :rules="infoRules" label-position="top" class="profile-form">
            <div class="form-grid">
              <el-form-item label="用户ID">
                <el-input :model-value="String(infoForm.user_id ?? '')" disabled class="soft-input" />
              </el-form-item>
              <el-form-item label="用户名" prop="username">
                <el-input v-model="infoForm.username" maxlength="20" class="soft-input" placeholder="2-20位" />
              </el-form-item>
              <el-form-item label="昵称" prop="nickname" required>
                <el-input v-model="infoForm.nickname" maxlength="30" class="soft-input" placeholder="请输入昵称" />
              </el-form-item>
              <el-form-item label="学号">
                <el-input :model-value="infoForm.student_no || '未填写'" disabled class="soft-input" />
              </el-form-item>
              <el-form-item label="手机号" prop="phone">
                <el-input v-model="infoForm.phone" maxlength="11" class="soft-input" placeholder="11位手机号" />
              </el-form-item>
              <el-form-item label="邮箱" prop="email">
                <el-input v-model="infoForm.email" class="soft-input" placeholder="用于接收匹配通知" />
              </el-form-item>
            </div>
            <div class="form-actions">
              <el-button class="save-btn" :loading="infoSaving" @click="saveInfo">保存信息</el-button>
            </div>
          </el-form>
        </section>

        <!-- 修改密码表单 -->
        <section v-show="activeSection === 'password'" class="card form-card">
          <h3 class="section-title">修改密码</h3>
          <el-form ref="pwFormRef" :model="pwForm" :rules="pwRules" label-position="top" class="profile-form">
            <div class="form-grid">
              <el-form-item label="新密码" prop="password">
                <el-input v-model="pwForm.password" type="password" show-password class="soft-input" placeholder="6-30位新密码" />
              </el-form-item>
              <el-form-item label="确认新密码" prop="confirm">
                <el-input v-model="pwForm.confirm" type="password" show-password class="soft-input" placeholder="再次输入新密码" />
              </el-form-item>
            </div>
            <div class="form-actions">
              <el-button class="save-btn" :loading="pwSaving" @click="savePassword">保存密码</el-button>
            </div>
          </el-form>

          <div class="danger-zone">
            <p class="danger-desc">注销账号后所有物品将关闭，账号数据将保留但无法再登录。此操作不可恢复。</p>
            <el-button type="danger" plain size="small" :loading="deleting" @click="handleDeleteAccount">
              注销账号
            </el-button>
          </div>
        </section>

        <!-- 我的发布（历史记录，保留原有逻辑） -->
        <section ref="historyRef" class="card form-card">
          <h3 class="section-title">我发布的物品</h3>
          <div v-if="historyLoading" v-loading="historyLoading" style="min-height:120px"></div>
          <template v-else>
            <div v-if="myItems.length === 0 && myClaims.length === 0" class="history-empty">
              <el-empty description="暂无历史记录">
                <el-button type="primary" @click="$router.push('/publish')">去发布物品</el-button>
              </el-empty>
            </div>

            <div v-if="myItems.length > 0" class="history-group">
              <h4 class="history-group-title">我发布的物品 ({{ myItems.length }})</h4>
              <div v-for="item in myItems" :key="'i'+item.id" class="history-item" @click="$router.push(`/items/${item.id}`)">
                <div class="item-thumb" v-if="item.image_path">
                  <img :src="`/api/items/uploads/${item.image_path.split('/').pop()}`" :alt="item.title" />
                </div>
                <div v-else class="item-thumb placeholder">📄</div>
                <div class="item-info">
                  <span class="item-title">{{ item.title }}</span>
                  <span class="item-meta">{{ item.type === 'lost' ? '失物' : '拾物' }} · {{ item.category || '未分类' }} · {{ item.created_at }}</span>
                </div>
                <span :class="['status-tag', statusClass(item.status)]">{{ statusLabel(item.status) }}</span>
              </div>
            </div>

            <div v-if="myClaims.length > 0" class="history-group">
              <h4 class="history-group-title">我发起的申请 ({{ myClaims.length }})</h4>
              <div v-for="c in myClaims" :key="'c'+c.id" class="history-item claim-item" @click="goClaimLink(c.link)">
                <span class="claim-icon">📨</span>
                <div class="item-info">
                  <span class="item-title">{{ c.title }}</span>
                  <span class="item-meta">{{ c.created_at }}</span>
                </div>
              </div>
            </div>
          </template>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { updateProfile, getMe, getHistory, deleteAccount } from '@/api/auth'
import { ElMessage, ElMessageBox } from 'element-plus'
import { User, Lock, Box, Document, Bell, ChatDotSquare, WarningFilled, ChatLineRound } from '@element-plus/icons-vue'

const authStore = useAuthStore()
const router = useRouter()
const user = computed(() => authStore.user)
const userFirstLetter = computed(() => (user.value?.username || 'U')[0].toUpperCase())

const profile = ref({})
const activeSection = ref('info')
const historyRef = ref(null)

// 业务导航 Tabs：我的发布滚动到本页历史区，其余跳既有页面
const businessTabs = [
  { key: 'publish', label: '我的发布', icon: Box },
  { key: 'claims', label: '我的认领', icon: Document },
  { key: 'received', label: '收到的认领', icon: Bell },
  { key: 'comments', label: '我的留言', icon: ChatDotSquare },
  { key: 'reports', label: '我的举报', icon: WarningFilled },
  { key: 'announce', label: '系统公告', icon: ChatLineRound },
]

const goBusinessTab = (key) => {
  const targets = {
    publish: null,
    claims: '/claims',
    received: '/claims?tab=received',
    comments: '/notifications',
    reports: '/reports/mine',
    announce: '/',
  }
  const to = targets[key]
  if (to) router.push(to)
  else historyRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

// ====== 基本信息表单 ======
const infoFormRef = ref(null)
const infoSaving = ref(false)
const infoForm = reactive({ user_id: null, username: '', nickname: '', student_no: '', phone: '', email: '' })

const infoRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 2, max: 20, message: '用户名长度 2-20 位', trigger: 'blur' },
  ],
  nickname: [{ required: true, message: '请输入昵称', trigger: 'blur' }],
  phone: [{
    validator: (rule, value, callback) => {
      if (!value || /^1[3-9]\d{9}$/.test(value)) callback()
      else callback(new Error('手机号格式不正确'))
    },
    trigger: 'blur',
  }],
  email: [{
    validator: (rule, value, callback) => {
      if (!value || /^[\w.+-]+@[\w-]+(\.[\w-]+)+$/.test(value)) callback()
      else callback(new Error('邮箱格式不正确'))
    },
    trigger: 'blur',
  }],
}

const saveInfo = () => {
  infoFormRef.value.validate(async (valid) => {
    if (!valid) return
    infoSaving.value = true
    try {
      const unameChanged = infoForm.username.trim() !== (profile.value.username || '')
      await updateProfile({
        username: infoForm.username.trim(),
        nickname: infoForm.nickname.trim(),
        phone: infoForm.phone.trim(),
        email: infoForm.email.trim(),
      })
      if (unameChanged) {
        // 用户名入 JWT：变更后需重新登录（保留原有逻辑）
        ElMessage.success('信息已保存，用户名已更新，请重新登录')
        setTimeout(() => { authStore.logout(); window.location.href = '/login' }, 1500)
      } else {
        ElMessage.success('保存成功')
        authStore.fetchUser()
        loadProfile()
      }
    } catch {} finally { infoSaving.value = false }
  })
}

// ====== 修改密码表单 ======
const pwFormRef = ref(null)
const pwSaving = ref(false)
const pwForm = reactive({ password: '', confirm: '' })

const pwRules = {
  password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, max: 30, message: '密码长度 6-30 位', trigger: 'blur' },
  ],
  confirm: [{
    validator: (rule, value, callback) => {
      if (!value) callback(new Error('请再次输入新密码'))
      else if (value !== pwForm.password) callback(new Error('两次输入的密码不一致'))
      else callback()
    },
    trigger: 'blur',
  }],
}

const savePassword = () => {
  pwFormRef.value.validate(async (valid) => {
    if (!valid) return
    pwSaving.value = true
    try {
      await updateProfile({ password: pwForm.password })
      ElMessage.success('密码已更新，请重新登录')
      pwForm.password = ''
      pwForm.confirm = ''
      setTimeout(() => { authStore.logout(); window.location.href = '/login' }, 1500)
    } catch {} finally { pwSaving.value = false }
  })
}

// ====== 历史记录（保留原有逻辑） ======
const myItems = ref([])
const myClaims = ref([])
const historyLoading = ref(false)

const loadHistory = async () => {
  historyLoading.value = true
  try {
    const res = await getHistory()
    if (res.data) {
      myItems.value = res.data.my_items || []
      myClaims.value = res.data.my_claims || []
    }
  } catch {} finally { historyLoading.value = false }
}

const statusLabel = (s) => {
  const map = { active: '展示中', pending: '审核中', claimed: '已找回', rejected: '已驳回', closed: '已关闭' }
  return map[s] || s
}
const statusClass = (s) => {
  const map = { active: 's-active', pending: 's-pending', claimed: 's-claimed', rejected: 's-rejected', closed: 's-closed' }
  return map[s] || ''
}
const goClaimLink = (link) => {
  if (link) window.location.href = link
}

// ====== 注销账号（保留原有逻辑） ======
const deleting = ref(false)
const handleDeleteAccount = async () => {
  try {
    await ElMessageBox.confirm('注销后所有物品将关闭，账号数据将保留但无法再登录。此操作不可恢复。请输入用户名以确认。', '确认注销账号', {
      confirmButtonText: '确认注销', cancelButtonText: '取消', type: 'error',
      inputPattern: new RegExp(`^${user.value?.username}$`),
      inputErrorMessage: '请输入正确的用户名以确认',
      inputType: 'text',
      showInput: true
    })
    deleting.value = true
    await deleteAccount()
    ElMessage.success('账号已注销')
    authStore.logout()
    window.location.href = '/login'
  } catch {} finally { deleting.value = false }
}

// ====== 初始化 ======
const loadProfile = async () => {
  try {
    const res = await getMe()
    if (res.user) {
      profile.value = res.user
      infoForm.user_id = res.user.id
      infoForm.username = res.user.username || ''
      infoForm.nickname = res.user.nickname || ''
      infoForm.student_no = res.user.student_no || ''
      infoForm.phone = res.user.phone || ''
      infoForm.email = res.user.email || ''
    }
  } catch {}
}

onMounted(() => { loadProfile(); loadHistory() })
</script>

<style scoped>
/* ---- 顶部标题 ---- */
.page-header { margin-bottom: var(--space-4); }
.page-title { margin-bottom: var(--space-1); }

/* ---- 业务导航 Tabs（胶囊） ---- */
.business-tabs {
  display: flex;
  gap: var(--space-3);
  flex-wrap: wrap;
  margin-bottom: var(--space-5);
}
.biz-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 18px;
  border-radius: var(--radius-full);
  border: 1px solid var(--border-light);
  background: var(--bg-card);
  color: var(--text-secondary);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}
.biz-tab:hover {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}

/* ---- 左右分栏 ---- */
.profile-layout {
  display: flex;
  gap: var(--space-5);
  align-items: flex-start;
}
.profile-left { width: 25%; flex-shrink: 0; min-width: 200px; }
.profile-right { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: var(--space-5); }

/* ---- 通用卡片 ---- */
.card {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-xs);
}

/* ---- 头像卡 ---- */
.avatar-card {
  padding: var(--space-6) var(--space-4);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-5);
}
.avatar-placeholder {
  width: 84px; height: 84px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--el-color-primary), var(--el-color-primary-light-2));
  color: white;
  display: flex; align-items: center; justify-content: center;
  font-size: 32px; font-weight: 700;
}
.avatar-hint {
  font-size: 11px;
  color: var(--text-muted);
  margin: 0;
  text-align: center;
}

/* ---- 二级菜单 ---- */
.side-menu {
  padding: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.side-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-3);
  border: none;
  border-left: 3px solid transparent;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-secondary);
  font-size: var(--text-sm);
  cursor: pointer;
  text-align: left;
  transition: all var(--transition-fast);
  width: 100%;
}
.side-item:hover { background: var(--neutral-100); }
.side-item.active {
  color: var(--text-primary);
  font-weight: 600;
  border-left-color: #2c5e5b;
  background: var(--neutral-100);
}

/* ---- 表单卡 ---- */
.form-card { padding: var(--space-6); }
.section-title {
  font-size: var(--text-lg);
  font-weight: 600;
  margin: 0 0 var(--space-5);
  color: var(--text-primary);
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 var(--space-5);
}
.form-grid .el-form-item { margin-bottom: var(--space-4); }

/* 输入框：浅灰底 + 去边框 */
.soft-input :deep(.el-input__wrapper) {
  background: var(--neutral-50);
  box-shadow: 0 0 0 1px var(--border-light) inset;
}
.soft-input :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px var(--el-color-primary) inset;
}
.soft-input :deep(.el-input.is-disabled .el-input__wrapper) {
  background: var(--neutral-100);
}

/* ---- 保存按钮（深青） ---- */
.form-actions { margin-top: var(--space-2); }
.save-btn {
  background: #2c5e5b;
  border-color: #2c5e5b;
  color: #fff;
  border-radius: var(--radius-md);
  padding: 0 28px;
  height: 40px;
  font-weight: 600;
  transition: background var(--transition-fast);
}
.save-btn:hover {
  background: #234b48;
  border-color: #234b48;
  color: #fff;
}
.save-btn:active {
  background: #1b3a38;
  border-color: #1b3a38;
}

/* ---- 危险操作 ---- */
.danger-zone {
  margin-top: var(--space-5);
  border: 1px solid #FFCDD2;
  border-radius: var(--radius-md);
  padding: var(--space-4);
  background: #FFF5F5;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  flex-wrap: wrap;
}
.danger-desc { font-size: var(--text-sm); color: var(--text-tertiary); margin: 0; flex: 1; min-width: 220px; }

/* ---- 历史记录 ---- */
.history-empty { padding: var(--space-6) 0; }
.history-group { margin-bottom: var(--space-6); }
.history-group-title { font-size: var(--text-sm); font-weight: 600; color: var(--text-secondary); margin: 0 0 var(--space-3); }
.history-item {
  display: flex; align-items: center; gap: var(--space-3);
  padding: var(--space-3); border-radius: var(--radius-md);
  cursor: pointer; transition: background var(--transition-fast);
}
.history-item:hover { background: var(--neutral-100); }
.item-thumb {
  width: 48px; height: 48px; border-radius: var(--radius-md); overflow: hidden;
  background: var(--neutral-100); flex-shrink: 0;
  display: flex; align-items: center; justify-content: center; font-size: 20px;
}
.item-thumb img { width: 100%; height: 100%; object-fit: cover; }
.item-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.item-title { font-size: var(--text-sm); font-weight: 500; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.item-meta { font-size: var(--text-xs); color: var(--text-tertiary); }
.claim-icon { font-size: 20px; flex-shrink: 0; }

.status-tag {
  font-size: var(--text-xs); padding: 2px 8px; border-radius: var(--radius-full); font-weight: 500; white-space: nowrap;
}
.s-active { background: #E8F5E9; color: #2E7D32; }
.s-pending { background: #FFF3E0; color: #ED6C02; }
.s-claimed { background: #E8F5E9; color: #1B4D3E; }
.s-rejected { background: #FFEBEE; color: #D32F2F; }
.s-closed { background: var(--neutral-100); color: var(--text-tertiary); }

/* ---- Responsive ---- */
@media (max-width: 768px) {
  .profile-layout { flex-direction: column; }
  .profile-left { width: 100%; min-width: 0; }
  .avatar-card { flex-direction: row; gap: var(--space-4); }
  .form-grid { grid-template-columns: 1fr; }
}
</style>
