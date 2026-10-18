<template>
  <div class="page-container">
    <h1 class="page-title">{{ isEdit ? '编辑物品' : '发布物品' }}</h1>
    <p class="page-desc" v-if="!isEdit">填写物品信息，帮助失主更快找到失物</p>
    <div v-if="isEdit && existingStatus === 'rejected'" class="re-edit-notice">
      <el-icon><WarningFilled /></el-icon>
      <span>该物品上次审核未通过，修改后将重新提交审核</span>
    </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        @submit.prevent="submit"
        label-position="top"
        hide-required-asterisk
        class="publish-form"
      >
        <!-- 基本信息 -->
        <p class="form-section">基本信息</p>

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
          <p class="field-hint">与标题一起计入匹配文本向量；可用窗口约 {{ TEXT_TOWER_WINDOW }} 字，建议把关键特征前置。</p>
          <p v-if="descCharCount > TEXT_TOWER_WINDOW" class="field-hint field-hint-warn">
            <el-icon><WarningFilled /></el-icon>
            <span>已输入 {{ descCharCount }} 字：超出 {{ TEXT_TOWER_WINDOW }} 字的部分不影响匹配精度，建议把关键特征写在前 {{ TEXT_TOWER_WINDOW }} 字内。</span>
          </p>
        </el-form-item>

        <!-- 联系与位置 -->
        <p class="form-section">联系与位置</p>

        <div class="form-row">
          <el-form-item label="位置" prop="location" class="form-grow">
            <el-input v-model="form.location" placeholder="丢失或发现地点" size="large" />
          </el-form-item>
          <el-form-item label="联系方式" prop="contact" class="form-grow">
            <el-input v-model="form.contact" placeholder="手机号/微信/QQ等" size="large" />
          </el-form-item>
        </div>

        <!-- 图片上传（v3.6.0：1-3 张，拖拽排序，首图为封面） -->
        <p class="form-section">物品图片</p>
        <el-form-item>
          <input
            ref="fileInput"
            type="file"
            accept=".jpg,.jpeg,.png,.gif,.webp"
            @change="handleFileChange"
            style="display:none"
          />
          <div class="images-grid">
            <div
              v-for="(img, i) in imageList"
              :key="img.key"
              class="image-cell"
              :class="{ 'image-cell--dragging': dragIndex === i }"
              draggable="true"
              @dragstart="onDragStart(i, $event)"
              @dragover.prevent
              @drop="onDrop(i)"
              @dragend="dragIndex = null"
            >
              <img :src="img.previewUrl" class="image-cell-img" />
              <span v-if="i === 0" class="cover-tag">封面</span>
              <span class="image-index">{{ i + 1 }}</span>
              <el-button class="image-remove" circle size="small" type="danger" @click="removeImage(i)">
                <el-icon><Close /></el-icon>
              </el-button>
            </div>
            <div v-if="imageList.length < 3" class="image-add" @click="triggerUpload">
              <el-icon :size="24"><Plus /></el-icon>
              <span>添加图片</span>
            </div>
          </div>
          <p class="field-hint">最多 3 张，支持拖拽排序；第一张将作为封面（也是 AI 匹配的主图）。信息越完整，找回概率越高。</p>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" native-type="submit" :loading="submitting" size="large" class="submit-btn">
            {{ isEdit ? '保存修改' : '发布物品' }}
          </el-button>
        </el-form-item>
      </el-form>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { createItem, updateItem, getItem, getCategories } from '@/api/items'
import { getImageUrl, parseItemImages } from '@/utils/helpers'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from 'element-plus'
import { QuestionFilled, CircleCheckFilled, UploadFilled, WarningFilled, Plus, Close } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
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

// v3.6.0：多图状态 [{ key, name(已存文件名|null), file(新文件|null), previewUrl }]
const imageList = ref([])
const dragIndex = ref(null)
const existingStatus = ref('')
let imgSeq = 0

// 模型文本塔可用窗口（汉字）：物品文本向量由「标题 + ' ' + 描述」编码，
// 超出窗口的部分被**静默截断**，故仅提示、绝不拦截/截断用户输入。
const TEXT_TOWER_WINDOW = 50
const descCharCount = computed(() => (form.value.description || '').length)

const triggerUpload = () => {
  fileInput.value?.click()
}

const handleFileChange = (e) => {
  const selected = e.target.files[0]
  if (!selected) return
  if (imageList.value.length >= 3) {
    ElMessage.warning('最多上传 3 张图片')
    if (fileInput.value) fileInput.value.value = ''
    return
  }
  imageList.value.push({
    key: `new-${imgSeq++}`,
    name: null,
    file: selected,
    previewUrl: URL.createObjectURL(selected)
  })
  if (fileInput.value) fileInput.value.value = ''
}

const removeImage = (index) => {
  const [removed] = imageList.value.splice(index, 1)
  if (removed?.previewUrl) URL.revokeObjectURL(removed.previewUrl)
}

// 原生 HTML5 拖拽排序（零依赖）
const onDragStart = (index, e) => {
  dragIndex.value = index
  e.dataTransfer.effectAllowed = 'move'
  try { e.dataTransfer.setData('text/plain', String(index)) } catch { /* 部分浏览器只读 */ }
}

const onDrop = (targetIndex) => {
  const from = dragIndex.value
  if (from === null || from === targetIndex) return
  const [moved] = imageList.value.splice(from, 1)
  imageList.value.splice(targetIndex, 0, moved)
  dragIndex.value = null
}

onUnmounted(() => {
  imageList.value.forEach((img) => { if (img.previewUrl) URL.revokeObjectURL(img.previewUrl) })
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
      // v3.6.0：多图提交——保留的旧图（新顺序）走 keep，新图逐个走 images 字段
      const keptNames = imageList.value.filter((i) => i.name).map((i) => i.name)
      const newFiles = imageList.value.filter((i) => i.file).map((i) => i.file)
      if (isEdit.value && keptNames.length) {
        formData.append('keep', JSON.stringify(keptNames))
      }
      newFiles.forEach((f) => formData.append('images', f))

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
        // v3.6.1：已审核通过的物品不允许发布者再编辑（管理员除外），直接退回详情页
        if (data.item.review_status === 'approved' && !authStore.isAdmin) {
          ElMessage.warning('该物品已审核通过，无法修改；如需更正请删除后重新发布')
          router.replace(`/items/${route.query.edit}`)
          return
        }
        form.value = {
          type: data.item.type || 'lost',
          title: data.item.title || '',
          description: data.item.description || '',
          category: data.item.category || '其他',
          contact: data.item.contact || '',
          location: data.item.location || ''
        }
        // 加载已有图片列表（保持顺序，首图为封面）
        const existing = parseItemImages(data.item)
        imageList.value = existing.map((name, i) => ({
          key: `old-${name}`,
          name,
          file: null,
          previewUrl: getImageUrl(name)
        }))
        imgSeq = existing.length
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

/* 网页式平铺表单：无卡片容器，分区以左侧竖条标题区隔 */
.publish-form {
  display: flex;
  flex-direction: column;
}

.form-row {
  display: flex;
  gap: var(--space-5);
}

.form-grow {
  flex: 1;
}

.form-section {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  margin: var(--space-6) 0 var(--space-4);
  padding: 0 0 var(--space-2) var(--space-2);
  border-left: 3px solid var(--el-color-primary);
  border-bottom: 1px solid var(--border-light);
}

.field-hint {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  margin: var(--space-1) 0 0;
  line-height: 1.5;
}

.field-hint-warn {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  color: #E65100;
}

:deep(.el-form-item__label) {
  font-weight: 600;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  letter-spacing: 0.02em;
}

.submit-btn {
  width: 240px;
  margin-left: auto;
  height: 46px;
  font-size: var(--text-lg);
  font-weight: 600;
  letter-spacing: 0.03em;
  border-radius: var(--radius-md);
  margin-top: var(--space-3);
}

@media (max-width: 640px) {
  .submit-btn { width: 100%; }
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

/* v3.6.0：多图网格 + 拖拽排序 */
.images-grid {
  display: flex;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.image-cell {
  position: relative;
  width: 110px;
  height: 110px;
  border-radius: var(--radius-md);
  overflow: hidden;
  border: 1px solid var(--border-default);
  cursor: grab;
  background: var(--neutral-100);
}

.image-cell--dragging {
  opacity: 0.5;
  border-color: var(--el-color-primary);
}

.image-cell-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
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

.image-index {
  position: absolute;
  top: 4px;
  left: 4px;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  font-size: 11px;
  padding: 1px 7px;
  border-radius: var(--radius-full);
}

.image-remove {
  position: absolute;
  top: 4px;
  right: 4px;
}

.image-add {
  width: 110px;
  height: 110px;
  border: 2px dashed var(--border-default);
  border-radius: var(--radius-md);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-1);
  color: var(--text-muted);
  cursor: pointer;
  font-size: var(--text-xs);
  transition: all var(--transition-base);
}

.image-add:hover {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}

@media (max-width: 640px) {
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
