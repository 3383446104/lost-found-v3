<template>
  <div class="page-container">
    <!-- 顶部标题 -->
    <div class="page-header">
      <h1 class="page-title">个人中心</h1>
      <p class="page-desc">管理您的账户信息与业务入口</p>
    </div>

    <!-- 主体：左右分栏（左 1/4 侧边栏，右 3/4 内容） -->
    <div class="profile-layout">
      <!-- 左侧：头像卡 + 统一侧边栏 -->
      <aside class="profile-left">
        <div class="card avatar-card">
          <div class="avatar-placeholder">{{ userFirstLetter }}</div>
          <p class="avatar-hint">支持 JPG/PNG，建议 1:1 比例</p>
        </div>

        <div class="card side-menu">
          <button
            v-for="item in sideItems"
            :key="item.key"
            class="side-item"
            :class="{ active: activeSection === item.key }"
            @click="activeSection = item.key"
          >
            <el-icon :size="16"><component :is="item.icon" /></el-icon>
            <span>{{ item.label }}</span>
          </button>
        </div>
      </aside>

      <!-- 右侧：内容区 -->
      <div class="profile-right">
        <!-- 基本信息（默认）：展示个人账户信息 -->
        <section v-show="activeSection === 'info'" class="card form-card">
          <h3 class="section-title">基本信息</h3>
          <div class="info-grid">
            <div class="info-row"><span class="info-label">用户ID</span><span class="info-value">{{ profile.id ?? '—' }}</span></div>
            <div class="info-row"><span class="info-label">用户名</span><span class="info-value">{{ profile.username || '—' }}</span></div>
            <div class="info-row"><span class="info-label">昵称</span><span class="info-value">{{ profile.nickname || '未填写' }}</span></div>
            <div class="info-row"><span class="info-label">学号</span><span class="info-value">{{ profile.student_no || '未填写' }}</span></div>
            <div class="info-row"><span class="info-label">手机号</span><span class="info-value">{{ profile.phone || '未填写' }}</span></div>
            <div class="info-row"><span class="info-label">邮箱</span><span class="info-value">{{ profile.email || '未填写' }}</span></div>
            <div class="info-row"><span class="info-label">角色</span><span class="info-value">{{ profile.role === 'admin' ? '管理员' : '普通用户' }}</span></div>
            <div class="info-row"><span class="info-label">加入时间</span><span class="info-value">{{ profile.created_at || '—' }}</span></div>
          </div>
        </section>

        <!-- 账号设置：修改账户信息 + 注销账号 -->
        <section v-show="activeSection === 'account'" class="card form-card">
          <h3 class="section-title">账号设置</h3>
          <el-form ref="infoFormRef" :model="infoForm" :rules="infoRules" label-position="top" class="profile-form">
            <div class="form-grid">
              <el-form-item label="用户名" prop="username">
                <el-input v-model="infoForm.username" maxlength="20" class="soft-input" placeholder="2-20位" />
              </el-form-item>
              <el-form-item label="昵称" prop="nickname" required>
                <el-input v-model="infoForm.nickname" maxlength="30" class="soft-input" placeholder="请输入昵称" />
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

          <el-form ref="pwFormRef" :model="pwForm" :rules="pwRules" label-position="top" class="profile-form pw-form">
            <h4 class="sub-title">修改密码</h4>
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

        <!-- 我的发布：查看和管理我发布的物品 -->
        <section v-show="activeSection === 'publish'" class="card form-card">
          <h3 class="section-title">我的发布</h3>
          <div v-if="publishLoading" v-loading="publishLoading" style="min-height:120px"></div>
          <el-empty v-else-if="!myItems.length" description="暂无发布记录">
            <el-button type="primary" @click="$router.push('/publish')">去发布物品</el-button>
          </el-empty>
          <div v-else class="history-group">
            <div v-for="item in myItems" :key="item.id" class="history-item">
              <div class="item-thumb" v-if="item.image_path">
                <img :src="`/api/items/uploads/${item.image_path.split('/').pop()}`" :alt="item.title" />
              </div>
              <div v-else class="item-thumb placeholder">📄</div>
              <div class="item-info" @click="$router.push(`/items/${item.id}`)">
                <span class="item-title">{{ item.title }}</span>
                <span class="item-meta">{{ item.type === 'lost' ? '失物' : '拾物' }} · {{ item.category || '未分类' }} · {{ item.created_at }}</span>
              </div>
              <span :class="['status-tag', statusClass(item.status)]">{{ statusLabel(item.status) }}</span>
              <div class="item-actions">
                <el-button size="small" text type="primary" @click="editItem(item.id)">编辑</el-button>
                <el-button
                  v-if="item.status === 'active'"
                  size="small" text type="success"
                  @click="markFound(item)"
                >{{ item.type === 'lost' ? '标记已找回' : '标记已归还' }}</el-button>
                <el-button size="small" text type="danger" @click="removeItem(item)">删除</el-button>
              </div>
            </div>
          </div>
        </section>

        <!-- 认领中心：我的申请 + 收到的申请（复用认领面板） -->
        <section v-show="activeSection === 'claims'" class="card form-card">
          <h3 class="section-title">认领中心</h3>
          <ClaimsPanel />
        </section>

        <!-- 我的留言：查看和管理自己发表的留言 -->
        <section v-show="activeSection === 'comments'" class="card form-card">
          <h3 class="section-title">我的留言</h3>
          <div v-if="commentLoading" v-loading="commentLoading" style="min-height:120px"></div>
          <el-empty v-else-if="!myCommentList.length" description="暂无留言" />
          <div v-else class="comment-list">
            <div v-for="c in myCommentList" :key="c.id" class="comment-item">
              <div class="comment-head">
                <el-tag size="small" :type="c.status === 1 ? 'success' : 'info'" effect="plain">
                  {{ c.status === 1 ? '正常' : '已隐藏' }}
                </el-tag>
                <span class="comment-time">{{ c.created_at }}</span>
              </div>
              <p class="comment-content">{{ c.content }}</p>
              <div class="comment-foot">
                <span class="comment-item-link" @click="$router.push(`/items/${c.item_id}`)">
                  所属物品：{{ c.item_title || '（已删除）' }}
                </span>
                <el-button size="small" text type="danger" @click="removeComment(c)">删除</el-button>
              </div>
            </div>
          </div>
        </section>

        <!-- 我的举报：查看举报信息与处理进度（复用举报面板） -->
        <section v-show="activeSection === 'reports'" class="card form-card">
          <h3 class="section-title">我的举报</h3>
          <MyReportsPanel />
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { updateProfile, getMe, deleteAccount } from '@/api/auth'
import { getItems, deleteItem, markClaimed } from '@/api/items'
import { myComments, deleteComment } from '@/api/comments'
import { ElMessage, ElMessageBox } from 'element-plus'
import { User, Setting, Box, Document, ChatDotSquare, WarningFilled } from '@element-plus/icons-vue'
import ClaimsPanel from '@/components/ClaimsPanel.vue'
import MyReportsPanel from '@/components/MyReportsPanel.vue'

const authStore = useAuthStore()
const router = useRouter()
const user = computed(() => authStore.user)
const userFirstLetter = computed(() => (user.value?.username || 'U')[0].toUpperCase())

const profile = ref({})
const activeSection = ref('info')

// 侧边栏（统一从上到下）
const sideItems = [
  { key: 'info', label: '基本信息', icon: User },
  { key: 'account', label: '账号设置', icon: Setting },
  { key: 'publish', label: '我的发布', icon: Box },
  { key: 'claims', label: '认领中心', icon: Document },
  { key: 'comments', label: '我的留言', icon: ChatDotSquare },
  { key: 'reports', label: '我的举报', icon: WarningFilled },
]

// ====== 账号设置：账户信息表单 ======
const infoFormRef = ref(null)
const infoSaving = ref(false)
const infoForm = reactive({ username: '', nickname: '', phone: '', email: '' })

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

// ====== 修改密码 ======
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

// ====== 我的发布 ======
const myItems = ref([])
const publishLoading = ref(false)

const loadMyItems = async () => {
  publishLoading.value = true
  try {
    const res = await getItems({ user_id: authStore.user?.id, limit: 50 })
    myItems.value = res.items || []
  } catch {} finally { publishLoading.value = false }
}

const editItem = (id) => router.push(`/publish?edit=${id}`)

const removeItem = async (item) => {
  try {
    await ElMessageBox.confirm(`确认删除「${item.title}」？此操作不可恢复。`, '删除物品', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'error'
    })
    await deleteItem(item.id)
    ElMessage.success('已删除')
    loadMyItems()
  } catch {}
}

const markFound = async (item) => {
  const label = item.type === 'lost' ? '已找回' : '已归还'
  try {
    await ElMessageBox.confirm(`确认将该物品标记为「${label}」？`, `标记${label}`, {
      confirmButtonText: '确认', cancelButtonText: '取消', type: 'success'
    })
    await markClaimed(item.id)
    ElMessage.success(`已标记为${label}`)
    loadMyItems()
  } catch {}
}

const statusLabel = (s) => {
  const map = { active: '展示中', pending: '审核中', claiming: '认领中', claimed: '已找回', rejected: '已驳回', closed: '已关闭', done: '已完成' }
  return map[s] || s
}
const statusClass = (s) => {
  const map = { active: 's-active', pending: 's-pending', claiming: 's-claiming', claimed: 's-claimed', rejected: 's-rejected', closed: 's-closed', done: 's-claimed' }
  return map[s] || ''
}

// ====== 我的留言 ======
const myCommentList = ref([])
const commentLoading = ref(false)

const loadMyComments = async () => {
  commentLoading.value = true
  try {
    const res = await myComments({ page: 1, size: 50 })
    myCommentList.value = res.comments || []
  } catch {} finally { commentLoading.value = false }
}

const removeComment = async (c) => {
  try {
    await ElMessageBox.confirm('确认删除这条留言？', '删除留言', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning'
    })
    await deleteComment(c.id)
    ElMessage.success('已删除')
    loadMyComments()
  } catch {}
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
      infoForm.username = res.user.username || ''
      infoForm.nickname = res.user.nickname || ''
      infoForm.phone = res.user.phone || ''
      infoForm.email = res.user.email || ''
    }
  } catch {}
}

onMounted(() => { loadProfile(); loadMyItems(); loadMyComments() })
</script>

<style scoped>
/* ---- 顶部标题 ---- */
.page-header { margin-bottom: var(--space-4); }
.page-title { margin-bottom: var(--space-1); }

/* ---- 左右分栏 ---- */
.profile-layout {
  display: flex;
  gap: var(--space-5);
  align-items: flex-start;
}
.profile-left { width: 25%; flex-shrink: 0; min-width: 200px; }
.profile-right { flex: 1; min-width: 0; }

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

/* ---- 侧边栏菜单 ---- */
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

/* ---- 内容卡 ---- */
.form-card { padding: var(--space-6); }
.section-title {
  font-size: var(--text-lg);
  font-weight: 600;
  margin: 0 0 var(--space-5);
  color: var(--text-primary);
}
.sub-title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-secondary);
  margin: var(--space-6) 0 var(--space-4);
  padding-top: var(--space-5);
  border-top: 1px solid var(--border-light);
}

/* ---- 基本信息展示 ---- */
.info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-2) var(--space-6);
}
.info-row {
  display: flex;
  justify-content: space-between;
  gap: var(--space-4);
  padding: var(--space-3) 0;
  border-bottom: 1px solid var(--border-light);
}
.info-label { font-size: var(--text-sm); color: var(--text-tertiary); flex-shrink: 0; }
.info-value { font-size: var(--text-sm); color: var(--text-primary); font-weight: 500; text-align: right; }

/* ---- 表单 ---- */
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 var(--space-5);
}
.form-grid .el-form-item { margin-bottom: var(--space-4); }

.soft-input :deep(.el-input__wrapper) {
  background: var(--neutral-50);
  box-shadow: 0 0 0 1px var(--border-light) inset;
}
.soft-input :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px var(--el-color-primary) inset;
}

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

/* ---- 我的发布 ---- */
.history-group { display: flex; flex-direction: column; gap: var(--space-3); }
.history-item {
  display: flex; align-items: center; gap: var(--space-3);
  padding: var(--space-3); border-radius: var(--radius-md);
  border: 1px solid var(--border-light);
  transition: background var(--transition-fast);
  flex-wrap: wrap;
}
.history-item:hover { background: var(--neutral-50); }
.item-thumb {
  width: 48px; height: 48px; border-radius: var(--radius-md); overflow: hidden;
  background: var(--neutral-100); flex-shrink: 0;
  display: flex; align-items: center; justify-content: center; font-size: 20px;
}
.item-thumb img { width: 100%; height: 100%; object-fit: cover; }
.item-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; cursor: pointer; }
.item-title { font-size: var(--text-sm); font-weight: 500; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.item-meta { font-size: var(--text-xs); color: var(--text-tertiary); }
.item-actions { display: flex; gap: 2px; flex-shrink: 0; }

.status-tag {
  font-size: var(--text-xs); padding: 2px 8px; border-radius: var(--radius-full); font-weight: 500; white-space: nowrap;
}
.s-active { background: #E8F5E9; color: #2E7D32; }
.s-pending { background: #FFF3E0; color: #ED6C02; }
.s-claiming { background: #FFF8E1; color: #B26A00; }
.s-claimed { background: #E8F5E9; color: #1B4D3E; }
.s-rejected { background: #FFEBEE; color: #D32F2F; }
.s-closed { background: var(--neutral-100); color: var(--text-tertiary); }

/* ---- 我的留言 ---- */
.comment-list { display: flex; flex-direction: column; gap: var(--space-3); }
.comment-item {
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  background: var(--bg-card);
}
.comment-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-2);
}
.comment-time { font-size: var(--text-xs); color: var(--text-muted); }
.comment-content {
  font-size: var(--text-sm);
  color: var(--text-primary);
  line-height: 1.7;
  margin: 0 0 var(--space-3);
  white-space: pre-wrap;
  word-break: break-all;
}
.comment-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  border-top: 1px dashed var(--border-light);
  padding-top: var(--space-2);
}
.comment-item-link {
  font-size: var(--text-xs);
  color: var(--el-color-primary);
  cursor: pointer;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.comment-item-link:hover { text-decoration: underline; }

/* ---- Responsive ---- */
@media (max-width: 768px) {
  .profile-layout { flex-direction: column; }
  .profile-left { width: 100%; min-width: 0; }
  .avatar-card { flex-direction: row; gap: var(--space-4); }
  .form-grid, .info-grid { grid-template-columns: 1fr; }
  .item-actions { width: 100%; justify-content: flex-end; }
}
</style>
