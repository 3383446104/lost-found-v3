<template>
  <div class="page-container">
    <h1 class="page-title">个人信息</h1>

    <!-- 个人信息横幅 -->
    <div class="profile-banner">
      <div class="avatar-placeholder">{{ userFirstLetter }}</div>
      <div class="banner-info">
        <div class="banner-name-row">
          <h2 class="user-name">{{ user?.username }}</h2>
          <span class="role-badge">{{ user?.role === 'admin' ? '管理员' : '普通用户' }}</span>
        </div>
        <p class="banner-meta">ID: {{ profile?.id }} · {{ profile?.created_at || '—' }} 加入</p>
      </div>
    </div>

    <!-- 设置区域：桌面端左侧导航 + 右侧内容 / 移动端 Tab 切换 -->
    <div class="settings-layout">
      <!-- 桌面端左侧导航 -->
      <nav class="settings-nav desktop-only">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          :class="['nav-item', { active: activeTab === tab.key }]"
          @click="activeTab = tab.key"
        >
          <el-icon v-if="tab.icon" :size="16"><component :is="tab.icon" /></el-icon>
          {{ tab.label }}
        </button>
        <div class="nav-divider"></div>
        <button
          :class="['nav-item danger', { active: activeTab === 'danger' }]"
          @click="activeTab = 'danger'"
        >
          <el-icon :size="16"><WarningFilled /></el-icon>
          危险操作
        </button>
      </nav>

      <!-- 移动端 Tab -->
      <div class="mobile-tabs mobile-only">
        <el-tabs v-model="activeTab" @tab-change="handleTabChange">
          <el-tab-pane v-for="tab in tabs" :key="tab.key" :label="tab.label" :name="tab.key" />
        </el-tabs>
      </div>

      <!-- 右侧内容区 -->
      <div class="settings-content">
        <!-- 账户设置 -->
        <section v-show="activeTab === 'account'" class="settings-section">
          <h3 class="section-title">账户设置</h3>

          <div class="settings-row">
            <span class="row-label">用户名</span>
            <div class="row-right">
              <template v-if="!editingUsername">
                <span class="row-value">{{ user?.username }}</span>
                <el-button size="small" text type="primary" @click="startEditUsername">编辑</el-button>
              </template>
              <template v-else>
                <el-input v-model="unameForm.username" size="small" placeholder="2-20位新用户名" style="width:180px" />
                <el-button size="small" type="primary" @click="saveUsername" :loading="unameLoading">保存</el-button>
                <el-button size="small" @click="cancelEditUsername">取消</el-button>
              </template>
            </div>
          </div>

          <div class="settings-row">
            <span class="row-label">密码</span>
            <div class="row-right">
              <template v-if="!editingPassword">
                <span class="row-value">••••••••</span>
                <el-button size="small" text type="primary" @click="editingPassword = true">修改</el-button>
              </template>
              <template v-else>
                <div class="pw-fields">
                  <el-input v-model="pwForm.password" type="password" size="small" placeholder="6-30位新密码" show-password />
                  <div class="row-actions">
                    <el-button size="small" type="primary" @click="savePassword" :loading="pwLoading">保存</el-button>
                    <el-button size="small" @click="editingPassword = false">取消</el-button>
                  </div>
                </div>
              </template>
            </div>
          </div>
        </section>

        <!-- 联系方式 -->
        <section v-show="activeTab === 'contact'" class="settings-section">
          <h3 class="section-title">联系方式</h3>
          <p class="section-hint">💡 手机号将在认领/归还申请中展示给对方，邮箱用于接收匹配通知。</p>

          <div class="settings-row">
            <span class="row-label">手机号</span>
            <div class="row-right">
              <template v-if="!editingPhone">
                <span class="row-value">{{ contactForm.phone || '未填写' }}</span>
                <el-button size="small" text type="primary" @click="startEditPhone">编辑</el-button>
              </template>
              <template v-else>
                <el-input v-model="contactForm.phone" size="small" placeholder="11位手机号" style="width:180px" />
                <el-button size="small" type="primary" @click="saveContact('phone')" :loading="contactLoading">保存</el-button>
                <el-button size="small" @click="cancelEditPhone">取消</el-button>
              </template>
            </div>
          </div>

          <div class="settings-row">
            <span class="row-label">邮箱</span>
            <div class="row-right">
              <template v-if="!editingEmail">
                <span class="row-value">{{ contactForm.email || '未填写' }}</span>
                <el-button size="small" text type="primary" @click="startEditEmail">编辑</el-button>
              </template>
              <template v-else>
                <el-input v-model="contactForm.email" size="small" placeholder="用于接收匹配通知" style="width:220px" />
                <el-button size="small" type="primary" @click="saveContact('email')" :loading="contactLoading">保存</el-button>
                <el-button size="small" @click="cancelEditEmail">取消</el-button>
              </template>
            </div>
          </div>
        </section>

        <!-- 历史记录 -->
        <section v-show="activeTab === 'history'" class="settings-section">
          <h3 class="section-title">历史记录</h3>
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

        <!-- 危险操作 -->
        <section v-show="activeTab === 'danger'" class="settings-section danger-zone">
          <h3 class="section-title" style="color:var(--el-color-danger)">⚠️ 危险操作</h3>
          <div class="danger-card">
            <p class="danger-desc">注销账号后所有物品将关闭，账号数据将保留但无法再登录。此操作不可恢复。</p>
            <el-button type="danger" @click="handleDeleteAccount" :loading="deleting" size="large">
              确认注销账号
            </el-button>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { updateProfile, getMe, getHistory, deleteAccount } from '@/api/auth'
import { ElMessage, ElMessageBox } from 'element-plus'
import { User, Phone, Clock, WarningFilled } from '@element-plus/icons-vue'

const authStore = useAuthStore()
const user = computed(() => authStore.user)
const userFirstLetter = computed(() => (user.value?.username || 'U')[0].toUpperCase())

const profile = ref({})
const activeTab = ref('account')

const tabs = [
  { key: 'account', label: '账户设置', icon: User },
  { key: 'contact', label: '联系方式', icon: Phone },
  { key: 'history', label: '历史记录', icon: Clock },
]

// ====== Account ======
const editingUsername = ref(false)
const editingPassword = ref(false)
const unameForm = reactive({ username: '' })
const pwForm = reactive({ password: '' })
const unameLoading = ref(false)
const pwLoading = ref(false)

const startEditUsername = () => {
  unameForm.username = user.value?.username || ''
  editingUsername.value = true
}
const cancelEditUsername = () => { editingUsername.value = false }
const saveUsername = async () => {
  const v = unameForm.username.trim()
  if (v.length < 2 || v.length > 20) { ElMessage.warning('用户名2-20位'); return }
  unameLoading.value = true
  try {
    await updateProfile({ username: v })
    ElMessage.success('用户名已更新，请重新登录')
    setTimeout(() => { authStore.logout(); window.location.href = '/login' }, 1500)
  } catch {} finally { unameLoading.value = false }
}

const savePassword = async () => {
  if (pwForm.password.length < 6 || pwForm.password.length > 30) { ElMessage.warning('密码6-30位'); return }
  pwLoading.value = true
  try {
    await updateProfile({ password: pwForm.password })
    ElMessage.success('密码已更新，请重新登录')
    pwForm.password = ''
    setTimeout(() => { authStore.logout(); window.location.href = '/login' }, 1500)
  } catch {} finally { pwLoading.value = false }
}

// ====== Contact ======
const contactForm = reactive({ phone: '', email: '' })
const editingPhone = ref(false)
const editingEmail = ref(false)
const contactLoading = ref(false)
let phoneBackup = ''
let emailBackup = ''

const startEditPhone = () => { phoneBackup = contactForm.phone; editingPhone.value = true }
const cancelEditPhone = () => { contactForm.phone = phoneBackup; editingPhone.value = false }
const startEditEmail = () => { emailBackup = contactForm.email; editingEmail.value = true }
const cancelEditEmail = () => { contactForm.email = emailBackup; editingEmail.value = false }
const saveContact = async (field) => {
  contactLoading.value = true
  try {
    const payload = {}
    if (field === 'phone') payload.phone = contactForm.phone
    if (field === 'email') payload.email = contactForm.email
    await updateProfile(payload)
    ElMessage.success('已更新')
    editingPhone.value = false
    editingEmail.value = false
    authStore.fetchUser()
    loadProfile()
  } catch {} finally { contactLoading.value = false }
}

// ====== History ======
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

// ====== Delete Account ======
const deleting = ref(false)
const handleDeleteAccount = async () => {
  try {
    await ElMessageBox.confirm('注销后所有物品将关闭，账号数据将保留但无法再登录。此操作不可恢复。请输入用户名以确认。', '⚠️ 确认注销账号', {
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

// ====== Init ======
const loadProfile = async () => {
  try {
    const res = await getMe()
    if (res.user) {
      profile.value = res.user
      contactForm.phone = res.user.phone || ''
      contactForm.email = res.user.email || ''
    }
  } catch {}
}

onMounted(() => { loadProfile(); loadHistory() })
</script>

<style scoped>
/* ---- Banner ---- */
.profile-banner {
  display: flex;
  align-items: center;
  gap: var(--space-5);
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-xl);
  padding: var(--space-6);
  margin-bottom: var(--space-6);
  box-shadow: var(--shadow-xs);
}

.avatar-placeholder {
  width: 64px; height: 64px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--el-color-primary), var(--el-color-primary-light-2));
  color: white;
  display: flex; align-items: center; justify-content: center;
  font-size: 24px; font-weight: 700;
  flex-shrink: 0;
}

.banner-info { flex: 1; min-width: 0; }
.banner-name-row { display: flex; align-items: center; gap: var(--space-3); margin-bottom: 4px; }
.user-name { font-size: var(--text-xl); font-weight: 700; margin: 0; color: var(--text-primary); }
.role-badge {
  font-size: var(--text-xs); color: var(--text-tertiary);
  background: var(--neutral-100); padding: 2px 10px; border-radius: var(--radius-full); font-weight: 500;
}
.banner-meta { font-size: var(--text-sm); color: var(--text-tertiary); margin: 0; }

/* ---- Settings Layout ---- */
.settings-layout { display: flex; gap: var(--space-6); align-items: flex-start; }
.settings-nav { width: 180px; flex-shrink: 0; display: flex; flex-direction: column; gap: 2px; }
.desktop-only { display: flex; }
.mobile-only { display: none; }

.nav-item {
  display: flex; align-items: center; gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border: none; border-radius: var(--radius-md);
  background: transparent; color: var(--text-secondary);
  font-size: var(--text-sm); font-weight: 500; cursor: pointer;
  transition: all var(--transition-fast);
  text-align: left;
}
.nav-item:hover { background: var(--neutral-100); color: var(--text-primary); }
.nav-item.active { background: var(--neutral-100); color: var(--el-color-primary); font-weight: 600; }
.nav-item.danger.active { color: var(--el-color-danger); }
.nav-divider { height: 1px; background: var(--border-light); margin: var(--space-2) 0; }

/* ---- Settings Content ---- */
.settings-content { flex: 1; min-width: 0; }
.settings-section {
  background: var(--bg-card); border: 1px solid var(--border-light);
  border-radius: var(--radius-xl); padding: var(--space-6); box-shadow: var(--shadow-xs);
}
.section-title { font-size: var(--text-lg); font-weight: 600; margin: 0 0 var(--space-1); color: var(--text-primary); }
.section-hint { font-size: var(--text-sm); color: var(--text-tertiary); margin: 0 0 var(--space-5); }

.settings-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: var(--space-4) 0;
  border-bottom: 1px solid var(--border-light);
}
.settings-row:last-child { border-bottom: none; }
.row-label { font-size: var(--text-sm); color: var(--text-secondary); font-weight: 500; flex-shrink: 0; width: 70px; }
.row-right { display: flex; align-items: center; gap: var(--space-3); }
.row-value { font-size: var(--text-base); color: var(--text-primary); font-weight: 500; }
.pw-fields { display: flex; flex-direction: column; gap: var(--space-2); flex: 1; }
.row-actions { display: flex; gap: var(--space-2); }

/* ---- History ---- */
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

.status-tag {
  font-size: var(--text-xs); padding: 2px 8px; border-radius: var(--radius-full); font-weight: 500; white-space: nowrap;
}
.s-active { background: #E8F5E9; color: #2E7D32; }
.s-pending { background: #FFF3E0; color: #ED6C02; }
.s-claimed { background: #E8F5E9; color: #1B4D3E; }
.s-rejected { background: #FFEBEE; color: #D32F2F; }
.s-closed { background: var(--neutral-100); color: var(--text-tertiary); }

/* ---- Danger Zone ---- */
.danger-zone .danger-card {
  border: 1px solid #FFCDD2; border-radius: var(--radius-md); padding: var(--space-5);
  background: #FFF5F5;
}
.danger-desc { font-size: var(--text-sm); color: var(--text-tertiary); margin: 0 0 var(--space-4); }

/* ---- Responsive ---- */
@media (max-width: 768px) {
  .profile-banner { padding: var(--space-4); }
  .avatar-placeholder { width: 48px; height: 48px; font-size: 18px; }
  .desktop-only { display: none; }
  .mobile-only { display: block; }
  .settings-layout { flex-direction: column; }
  .settings-content { width: 100%; }
  .settings-row { flex-direction: column; align-items: flex-start; gap: var(--space-2); }
  .row-label { width: auto; }
}
</style>
