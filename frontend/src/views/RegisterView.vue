<template>
  <div class="auth-page">
    <!-- 校园航拍背景 -->
    <div class="auth-bg">
      <div class="bg-overlay"></div>
    </div>

    <!-- 半透明注册卡片 -->
    <div class="auth-dialog">
      <div class="dialog-header">
        <svg width="44" height="44" viewBox="0 0 48 48" fill="none" class="dialog-logo">
          <rect width="48" height="48" rx="14" fill="#1B4D3E" opacity="0.92"/>
          <path d="M24 11c-5.5 0-10 4.5-10 10 0 6.5 10 16.5 10 16.5s10-10 10-16.5c0-5.5-4.5-10-10-10zm0 14c-2.2 0-4-1.8-4-4s1.8-4 4-4 4 1.8 4 4-1.8 4-4 4z" fill="white"/>
          <circle cx="34" cy="14" r="5" fill="#D4A853"/>
        </svg>
        <h1 class="dialog-title">校园失物检索平台</h1>
        <p class="dialog-subtitle">创建账号，开始寻回之旅</p>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        @submit.prevent="handleRegister"
        label-position="top"
        hide-required-asterisk
      >
        <el-form-item label="用户名" prop="username">
          <el-input
            v-model="form.username"
            placeholder="2-20位字母/数字/下划线/中文"
            :prefix-icon="User"
            size="large"
            clearable
          />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="6-30位密码"
            :prefix-icon="Lock"
            size="large"
            show-password
            clearable
          />
        </el-form-item>
        <el-form-item label="手机号" prop="phone">
          <el-input
            v-model="form.phone"
            placeholder="11位手机号（必填）"
            :prefix-icon="Phone"
            size="large"
            clearable
          />
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input
            v-model="form.email"
            placeholder="用于接收匹配通知（必填）"
            :prefix-icon="Message"
            size="large"
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
            注册
          </el-button>
        </el-form-item>
      </el-form>

      <div class="dialog-footer">
        已有账号？<router-link to="/login">去登录</router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { register } from '@/api/auth'
import { ElMessage } from 'element-plus'
import { User, Lock, Phone, Message } from '@element-plus/icons-vue'

const router = useRouter()
const formRef = ref(null)
const loading = ref(false)

const form = reactive({
  username: '',
  password: '',
  phone: '',
  email: ''
})

const validatePhone = (rule, value, callback) => {
  if (value && !/^1[3-9]\d{9}$/.test(value)) {
    callback(new Error('手机号格式不正确'))
  } else {
    callback()
  }
}

const validateEmail = (rule, value, callback) => {
  if (value && !/^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/.test(value)) {
    callback(new Error('邮箱格式不正确'))
  } else {
    callback()
  }
}

const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 2, max: 20, message: '长度 2-20 位', trigger: 'blur' },
    { pattern: /^[a-zA-Z0-9_一-龥]+$/, message: '只能包含字母、数字、下划线或中文', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 30, message: '长度 6-30 位', trigger: 'blur' }
  ],
  phone: [
    { required: true, message: '请输入手机号', trigger: 'blur' },
    { validator: validatePhone, trigger: 'blur' }
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { validator: validateEmail, trigger: 'blur' }
  ]
}

const handleRegister = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    try {
      await register(form)
      ElMessage.success('注册成功，请登录')
      router.push('/login')
    } catch (error) {
      // 错误已在拦截器处理
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

.auth-dialog {
  position: relative;
  z-index: 1;
  width: 420px;
  max-width: calc(100vw - 32px);
  padding: var(--space-8) var(--space-8);
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

.dialog-header {
  text-align: center;
  margin-bottom: var(--space-6);
}

.dialog-logo {
  margin-bottom: var(--space-3);
  filter: drop-shadow(0 2px 4px rgba(0,0,0,0.1));
}

.dialog-title {
  font-size: var(--text-xl);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 4px;
  letter-spacing: -0.01em;
}

.dialog-subtitle {
  font-size: var(--text-base);
  color: var(--text-tertiary);
  margin: 0;
}

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
}

.dialog-footer {
  text-align: center;
  font-size: var(--text-base);
  color: var(--text-tertiary);
  margin-top: var(--space-2);
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

@media (max-width: 480px) {
  .auth-dialog {
    padding: var(--space-6) var(--space-5);
    border-radius: var(--radius-lg);
  }
}
</style>
