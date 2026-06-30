<template>
  <div class="auth-page">
    <!-- 校园航拍背景 -->
    <div class="auth-bg">
      <div class="bg-overlay"></div>
    </div>

    <!-- 半透明登录卡片 -->
    <div class="auth-dialog">
      <div class="dialog-header">
        <svg width="48" height="48" viewBox="0 0 48 48" fill="none" class="dialog-logo">
          <rect width="48" height="48" rx="14" fill="#1B4D3E" opacity="0.92"/>
          <path d="M24 11c-5.5 0-10 4.5-10 10 0 6.5 10 16.5 10 16.5s10-10 10-16.5c0-5.5-4.5-10-10-10zm0 14c-2.2 0-4-1.8-4-4s1.8-4 4-4 4 1.8 4 4-1.8 4-4 4z" fill="white"/>
          <circle cx="34" cy="14" r="5" fill="#D4A853"/>
        </svg>
        <h1 class="dialog-title">校园失物智能寻回系统</h1>
        <p class="dialog-subtitle">登录以继续使用</p>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        @submit.prevent="handleLogin"
        label-position="top"
        hide-required-asterisk
      >
        <el-form-item label="用户名" prop="username">
          <el-input
            v-model="form.username"
            placeholder="请输入用户名"
            :prefix-icon="User"
            size="large"
            clearable
          />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            :prefix-icon="Lock"
            size="large"
            show-password
            clearable
          />
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            native-type="submit"
            :loading="loading"
            size="large"
            class="submit-btn"
          >
            登录
          </el-button>
        </el-form-item>
      </el-form>

      <div class="dialog-footer">
        还没有账号？<router-link to="/register">立即注册</router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { login } from '@/api/auth'
import { ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'

const router = useRouter()
const authStore = useAuthStore()
const formRef = ref(null)
const loading = ref(false)

const form = reactive({
  username: '',
  password: ''
})

const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 2, max: 20, message: '用户名长度 2-20 位', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 30, message: '密码长度 6-30 位', trigger: 'blur' }
  ]
}

const handleLogin = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    try {
      const res = await login(form)
      if (res.success) {
        authStore.setAuth(res.token, res.user)
        ElMessage.success('登录成功')
        router.push(res.user?.role === 'admin' ? '/admin' : '/items')
      } else {
        ElMessage.error(res.message || '登录失败')
      }
    } catch (error) {
      console.error('登录异常:', error)
    } finally {
      loading.value = false
    }
  })
}
</script>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  padding: var(--space-5);
}

/* ---- 校园航拍背景 ---- */
.auth-bg {
  position: fixed;
  inset: 0;
  z-index: 0;
  background-image: url('/campus-aerial.jpg');
  background-size: cover;
  background-position: center;
  background-repeat: no-repeat;
}

.bg-overlay {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    180deg,
    rgba(0, 0, 0, 0.45) 0%,
    rgba(0, 0, 0, 0.35) 50%,
    rgba(0, 0, 0, 0.40) 100%
  );
}

/* ---- 半透明卡片 ---- */
.auth-dialog {
  position: relative;
  z-index: 1;
  width: 400px;
  max-width: calc(100vw - 32px);
  padding: var(--space-10) var(--space-8);
  border-radius: var(--radius-xl);
  background: rgba(255, 255, 255, 0.76);
  backdrop-filter: blur(24px) saturate(150%);
  -webkit-backdrop-filter: blur(24px) saturate(150%);
  box-shadow:
    0 8px 32px rgba(0, 0, 0, 0.14),
    0 2px 8px rgba(0, 0, 0, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.5);
  border: 1px solid rgba(255, 255, 255, 0.45);
}

/* ---- 标题 ---- */
.dialog-header {
  text-align: center;
  margin-bottom: var(--space-8);
}

.dialog-logo {
  margin-bottom: var(--space-4);
  filter: drop-shadow(0 2px 4px rgba(0,0,0,0.1));
}

.dialog-title {
  font-size: var(--text-xl);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 4px;
  letter-spacing: -0.01em;
  line-height: 1.3;
}

.dialog-subtitle {
  font-size: var(--text-base);
  color: var(--text-tertiary);
  margin: 0;
}

/* ---- 表单 ---- */
:deep(.el-form-item__label) {
  font-weight: 600;
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.submit-btn {
  width: 100%;
  height: 44px;
  font-size: var(--text-lg);
  font-weight: 600;
  letter-spacing: 0.05em;
  border-radius: var(--radius-md);
  margin-top: var(--space-2);
}

.dialog-footer {
  text-align: center;
  font-size: var(--text-base);
  color: var(--text-tertiary);
  margin-top: var(--space-3);
}

.dialog-footer a {
  color: var(--el-color-primary);
  text-decoration: none;
  font-weight: 600;
  transition: opacity var(--transition-fast);
}

.dialog-footer a:hover {
  opacity: 0.8;
}

/* ---- 响应式 ---- */
@media (max-width: 480px) {
  .auth-dialog {
    padding: var(--space-8) var(--space-6);
    border-radius: var(--radius-lg);
  }
}
</style>
