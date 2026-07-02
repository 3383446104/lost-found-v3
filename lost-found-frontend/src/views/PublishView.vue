<template>
  <div class="page-container">
    <h1 class="page-title">{{ isEdit ? '编辑物品' : '发布物品' }}</h1>
    <p class="page-desc" v-if="!isEdit">填写物品信息，帮助失主更快找到失物</p>
    <div v-if="isEdit && existingStatus === 'rejected'" class="re-edit-notice">
      <el-icon><WarningFilled /></el-icon>
      <span>该物品上次审核未通过，修改后将重新提交审核</span>
    </div>

    <div class="publish-card">
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        @submit.prevent="submit"
        label-position="top"
        hide-required-asterisk
      >
        <!-- 类型选择 -->
        <el-form-item label="物品类型" prop="type">
          <el-radio-group v-model="form.type" size="large">
            <el-radio-button value="lost">
              <el-icon><QuestionFilled /></el-icon> 失物
            </el-radio-button>
            <el-radio-button value="found">
              <el-icon><CircleCheckFilled /></el-icon> 拾物
            </el-radio-button>
          </el-radio-group>
        </el-form-item>

        <div class="form-row">
          <el-form-item label="标题" prop="title" class="form-grow">
            <el-input v-model="form.title" placeholder="物品名称，2-50字" maxlength="50" show-word-limit size="large" />
          </el-form-item>
          <el-form-item label="分类" prop="category">
            <el-select v-model="form.category" placeholder="选择分类" style="width:160px" size="large">
              <el-option v-for="cat in categories" :key="cat" :label="cat" :value="cat" />
            </el-select>
          </el-form-item>
        </div>

        <el-form-item label="详细描述" prop="description">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="4"
            placeholder="描述物品的外观、特征、丢失/发现经过等..."
            maxlength="500"
            show-word-limit
          />
        </el-form-item>

        <div class="form-row">
          <el-form-item label="位置" prop="location" class="form-grow">
            <el-input v-model="form.location" placeholder="丢失或发现地点" size="large" />
          </el-form-item>
          <el-form-item label="联系方式" prop="contact" class="form-grow">
            <el-input v-model="form.contact" placeholder="手机号/微信/QQ等" size="large" />
          </el-form-item>
        </div>

        <!-- 图片上传 -->
        <el-form-item label="物品图片">
          <div class="upload-area" @click="triggerUpload">
            <input
              ref="fileInput"
              type="file"
              accept=".jpg,.jpeg,.png,.gif,.webp"
              @change="handleFileChange"
              style="display:none"
            />
            <template v-if="previewImageUrl">
              <img :src="previewImageUrl" class="upload-preview" />
              <div class="upload-overlay">
                <el-button text type="primary" @click.stop="clearPreview" size="small">重新选择</el-button>
              </div>
            </template>
            <template v-else-if="currentImageUrl">
              <img :src="currentImageUrl" class="upload-preview" />
              <div class="upload-overlay">
                <el-button text type="primary" @click.stop="triggerUpload" size="small">更换图片</el-button>
              </div>
            </template>
            <template v-else>
              <el-icon :size="40"><UploadFilled /></el-icon>
              <span class="upload-text">点击上传图片</span>
              <span class="upload-hint">支持 JPG、PNG、GIF、WebP，最大 5MB</span>
            </template>
          </div>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" native-type="submit" :loading="submitting" size="large" style="width:100%" class="submit-btn">
            {{ isEdit ? '保存修改' : '发布物品' }}
          </el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { createItem, updateItem, getItem, getCategories } from '@/api/items'
import { getImageUrl } from '@/utils/helpers'
import { ElMessage } from 'element-plus'
import { QuestionFilled, CircleCheckFilled, UploadFilled, WarningFilled } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const isEdit = computed(() => !!route.query.edit)
const categories = ref([])
const submitting = ref(false)
const formRef = ref(null)
const fileInput = ref(null)

const form = ref({
  type: 'lost',
  title: '',
  description: '',
  category: '其他',
  contact: '',
  location: ''
})

const file = ref(null)
const previewImageUrl = ref('')
const existingImagePath = ref('')
const existingStatus = ref('')

const currentImageUrl = computed(() => {
  return existingImagePath.value ? getImageUrl(existingImagePath.value) : ''
})

const triggerUpload = () => {
  fileInput.value?.click()
}

const handleFileChange = (e) => {
  const selected = e.target.files[0]
  if (!selected) return
  if (previewImageUrl.value) URL.revokeObjectURL(previewImageUrl.value)
  file.value = selected
  previewImageUrl.value = URL.createObjectURL(selected)
}

const clearPreview = () => {
  if (previewImageUrl.value) URL.revokeObjectURL(previewImageUrl.value)
  previewImageUrl.value = ''
  file.value = null
  if (fileInput.value) fileInput.value.value = ''
}

onUnmounted(() => {
  if (previewImageUrl.value) URL.revokeObjectURL(previewImageUrl.value)
})

const rules = {
  type: [{ required: true, message: '请选择类型', trigger: 'change' }],
  title: [
    { required: true, message: '请输入标题', trigger: 'blur' },
    { min: 2, max: 50, message: '标题长度 2-50 位', trigger: 'blur' }
  ],
  category: [{ required: true, message: '请选择分类', trigger: 'change' }],
  contact: [
    { required: true, message: '请填写联系方式', trigger: 'blur' }
  ]
}

const submit = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    submitting.value = true
    try {
      const formData = new FormData()
      const allowedKeys = ['type', 'title', 'description', 'category', 'contact', 'location']
      allowedKeys.forEach(key => {
        if (form.value[key] !== undefined && form.value[key] !== null) {
          formData.append(key, form.value[key])
        }
      })
      if (file.value) formData.append('image', file.value)

      if (isEdit.value) {
        await updateItem(route.query.edit, formData)
        ElMessage.success('修改已提交，等待重新审核')
      } else {
        await createItem(formData)
        ElMessage.success('发布成功，等待管理员审核')
      }
      router.push('/items')
    } catch (error) {
      console.error('提交失败:', error)
    } finally {
      submitting.value = false
    }
  })
}

onMounted(async () => {
  try {
    const res = await getCategories()
    categories.value = res.categories || []
  } catch {}

  if (isEdit.value) {
    try {
      const data = await getItem(route.query.edit)
      if (data.item) {
        form.value = {
          type: data.item.type || 'lost',
          title: data.item.title || '',
          description: data.item.description || '',
          category: data.item.category || '其他',
          contact: data.item.contact || '',
          location: data.item.location || ''
        }
        existingImagePath.value = data.item.image_path || ''
        existingStatus.value = data.item.status || ''
      }
    } catch {
      ElMessage.error('无法加载物品信息')
      router.push('/items')
    }
  }
})
</script>

<style scoped>
.re-edit-notice {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  background: #FFF3E0;
  border: 1px solid #FFE0B2;
  border-radius: var(--radius-md);
  color: #E65100;
  font-size: var(--text-sm);
  margin-bottom: var(--space-4);
  max-width: 640px;
  margin-left: auto;
  margin-right: auto;
}

.publish-card {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-xl);
  padding: var(--space-8);
  max-width: 640px;
  margin: 0 auto;
  box-shadow: var(--shadow-sm);
}

.form-row {
  display: flex;
  gap: var(--space-5);
}

.form-grow {
  flex: 1;
}

:deep(.el-form-item__label) {
  font-weight: 600;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  letter-spacing: 0.02em;
}

.submit-btn {
  height: 46px;
  font-size: var(--text-lg);
  font-weight: 600;
  letter-spacing: 0.03em;
  border-radius: var(--radius-md);
  margin-top: var(--space-3);
}

.upload-area {
  border: 2px dashed var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--space-8);
  text-align: center;
  cursor: pointer;
  transition: all var(--transition-base);
  min-height: 140px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  background: var(--neutral-50);
}

.upload-area:hover {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.upload-text {
  font-size: var(--text-md);
  color: var(--text-primary);
  font-weight: 500;
}

.upload-hint {
  font-size: var(--text-sm);
  color: var(--text-muted);
}

.upload-preview {
  max-width: 100%;
  max-height: 200px;
  object-fit: contain;
  border-radius: var(--radius-md);
}

.upload-overlay {
  margin-top: var(--space-3);
}

@media (max-width: 640px) {
  .publish-card {
    padding: var(--space-5);
    border-radius: var(--radius-lg);
  }
  .form-row {
    flex-direction: column;
    gap: var(--space-4);
  }
  .upload-area {
    padding: var(--space-5);
    min-height: 100px;
  }
}
</style>
