<template>
  <div class="page-container">
    <h1 class="page-title">个人信息</h1>

    <div class="profile-layout">
      <!-- 基本信息卡片 -->
      <div class="info-card">
        <div class="card-head">
          <div class="avatar-lg">{{ (user?.username || 'U')[0].toUpperCase() }}</div>
          <div>
            <h2 class="user-name">{{ user?.username }}</h2>
            <span class="user-role">{{ user?.role === 'admin' ? '管理员' : '普通用户' }}</span>
          </div>
        </div>
        <div class="info-list">
          <div class="info-row">
            <span class="info-label">用户 ID</span>
            <span class="info-val">{{ user?.id }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">注册时间</span>
            <span class="info-val">{{ profile?.created_at || '-' }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">手机号</span>
            <span class="info-val">{{ profile?.phone || '未填写' }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">邮箱</span>
            <span class="info-val">{{ profile?.email || '未填写' }}</span>
          </div>
        </div>
      </div>

      <!-- 修改资料 -->
      <div class="form-section">
        <!-- 修改密码 -->
        <div class="form-card">
          <h3 class="card-title">修改密码</h3>
          <el-form :model="pwForm" :rules="pwRules" ref="pwFormRef" label-position="top" @submit.prevent="updatePassword">
            <el-form-item label="新密码" prop="password">
              <el-input v-model="pwForm.password" type="password" placeholder="6-30位新密码" show-password size="large" />
            </el-form-item>
            <el-button type="primary" native-type="submit" :loading="pwLoading" size="large" style="width:100%">
              更新密码
            </el-button>
          </el-form>
        </div>

        <!-- 修改联系方式 -->
        <div class="form-card">
          <h3 class="card-title">联系方式</h3>
          <el-form :model="contactForm" ref="contactFormRef" label-position="top" @submit.prevent="updateContact">
            <el-form-item label="手机号">
              <el-input v-model="contactForm.phone" placeholder="11位手机号" size="large" />
            </el-form-item>
            <el-form-item label="邮箱">
              <el-input v-model="contactForm.email" placeholder="用于接收匹配通知" size="large" />
            </el-form-item>
            <el-button type="primary" native-type="submit" :loading="contactLoading" size="large" style="width:100%">
              更新联系方式
            </el-button>
          </el-form>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { updateProfile, getMe } from '@/api/auth'
import { ElMessage } from 'element-plus'

const authStore = useAuthStore()
const user = computed(() => authStore.user)
const profile = ref({})

const pwFormRef = ref(null)
const contactFormRef = ref(null)
const pwLoading = ref(false)
const contactLoading = ref(false)

const pwForm = reactive({ password: '' })
const pwRules = {
  password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, max: 30, message: '密码长度 6-30 位', trigger: 'blur' }
  ]
}

const contactForm = reactive({ phone: '', email: '' })

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

const updatePassword = async () => {
  if (!pwFormRef.value) return
  await pwFormRef.value.validate(async (valid) => {
    if (!valid) return
    pwLoading.value = true
    try {
      await updateProfile({ password: pwForm.password })
      ElMessage.success('密码已更新，请重新登录')
      pwForm.password = ''
      // 密码变更后强制重新登录
      setTimeout(() => {
        authStore.logout()
        window.location.href = '/login'
      }, 1500)
    } catch {
      // 拦截器已处理
    } finally {
      pwLoading.value = false
    }
  })
}

const updateContact = async () => {
  contactLoading.value = true
  try {
    await updateProfile({
      phone: contactForm.phone,
      email: contactForm.email
    })
    ElMessage.success('联系方式已更新')
    loadProfile()
  } catch {
    // 拦截器已处理
  } finally {
    contactLoading.value = false
  }
}

onMounted(loadProfile)
</script>

<style scoped>
.profile-layout {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: var(--space-6);
  align-items: start;
}

/* ---- 基本信息卡片 ---- */
.info-card {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-xl);
  padding: var(--space-6);
  box-shadow: var(--shadow-xs);
}

.card-head {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  margin-bottom: var(--space-6);
  padding-bottom: var(--space-5);
  border-bottom: 1px solid var(--border-light);
}

.avatar-lg {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--el-color-primary), var(--el-color-primary-light-2));
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-2xl);
  font-weight: 700;
  flex-shrink: 0;
}

.user-name {
  font-size: var(--text-xl);
  font-weight: 700;
  margin: 0 0 2px;
  color: var(--text-primary);
}

.user-role {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
  background: var(--neutral-100);
  padding: 2px 10px;
  border-radius: var(--radius-full);
  font-weight: 500;
}

.info-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.info-label {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

.info-val {
  font-size: var(--text-base);
  color: var(--text-primary);
  font-weight: 500;
}

/* ---- 表单区 ---- */
.form-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.form-card {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-xl);
  padding: var(--space-6);
  box-shadow: var(--shadow-xs);
}

.card-title {
  font-size: var(--text-lg);
  font-weight: 600;
  margin: 0 0 var(--space-5);
  color: var(--text-primary);
}

@media (max-width: 768px) {
  .profile-layout {
    grid-template-columns: 1fr;
  }
}
</style>
