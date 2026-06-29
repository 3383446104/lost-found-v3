<template>
  <div class="page-container">
    <h1 class="page-title">智能匹配</h1>
    <p class="page-desc">上传图片或输入文字描述，AI 将自动匹配最相似的物品</p>

    <div class="match-panel">
      <!-- 目标类型 -->
      <div class="panel-section">
        <label class="panel-label">匹配目标</label>
        <el-radio-group v-model="targetType" size="large">
          <el-radio-button value="found">
            <el-icon><Search /></el-icon> 拾物物品
          </el-radio-button>
          <el-radio-button value="lost">
            <el-icon><Search /></el-icon> 失物物品
          </el-radio-button>
        </el-radio-group>
      </div>

      <!-- 图片上传 -->
      <div class="panel-section">
        <label class="panel-label">上传图片</label>
        <div class="upload-area" @click="triggerUpload">
          <input
            ref="fileInput"
            type="file"
            accept=".jpg,.jpeg,.png,.gif,.webp"
            @change="handleFileSelected"
            style="display:none"
          />
          <template v-if="previewUrl">
            <img :src="previewUrl" class="upload-preview" />
            <div class="upload-overlay">
              <el-button text type="primary" @click.stop="clearPreview" size="small">重新选择</el-button>
            </div>
          </template>
          <template v-else>
            <el-icon :size="40"><UploadFilled /></el-icon>
            <span class="upload-text">点击上传图片</span>
            <span class="upload-hint">支持 JPG、PNG、GIF、WebP</span>
          </template>
        </div>
      </div>

      <!-- 文字描述 -->
      <div class="panel-section">
        <label class="panel-label">或输入文字描述</label>
        <el-input
          v-model="text"
          type="textarea"
          :rows="3"
          placeholder="描述物品特征，例如：黑色双肩包、带有红色挂件的钥匙串..."
          maxlength="300"
          show-word-limit
        />
      </div>

      <!-- 匹配按钮 -->
      <el-button
        type="primary"
        size="large"
        :loading="matching"
        @click="doMatch"
        :disabled="!imagePath && !text.trim()"
        class="match-btn"
      >
        <el-icon><Connection /></el-icon>
        {{ matching ? 'AI 匹配中...' : '开始智能匹配' }}
      </el-button>
    </div>

    <!-- 匹配结果 -->
    <div v-if="results.length" class="results-section">
      <h2 class="results-heading">
        匹配结果
        <span class="result-count">{{ results.length }} 条</span>
      </h2>
      <div class="card-grid">
        <div
          v-for="r in results"
          :key="r.id"
          class="result-card"
          @click="$router.push(`/items/${r.id}`)"
        >
          <div class="card-img">
            <img v-if="r.image_path" :src="getImageUrl(r.image_path)" :alt="r.title" />
            <div v-else class="img-placeholder">
              <el-icon :size="32"><PictureFilled /></el-icon>
            </div>
            <div class="similarity-badge">
              {{ (r.similarity * 100).toFixed(0) }}%
            </div>
          </div>
          <div class="card-body">
            <h3 class="card-title">{{ r.title }}</h3>
            <p class="card-desc" v-if="r.description">{{ r.description }}</p>
            <div class="card-meta" v-if="r.category">
              <span class="meta-cat">{{ r.category }}</span>
            </div>
            <div class="similarity-bar">
              <div class="similarity-track">
                <div
                  class="similarity-fill"
                  :style="{ width: (r.similarity * 100) + '%' }"
                ></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 空结果 -->
    <el-empty
      v-if="searched && !results.length"
      description="未找到匹配物品，请尝试调整描述或更换图片"
    />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { matchItems, tempUpload } from '@/api/items'
import { getImageUrl } from '@/utils/helpers'
import { ElMessage } from 'element-plus'
import { Search, UploadFilled, Connection, PictureFilled } from '@element-plus/icons-vue'

const text = ref('')
const targetType = ref('found')
const imagePath = ref('')
const previewUrl = ref('')
const fileInput = ref(null)
const results = ref([])
const matching = ref(false)
const searched = ref(false)

const triggerUpload = () => {
  fileInput.value?.click()
}

const handleFileSelected = async (e) => {
  const file = e.target.files[0]
  if (!file) return
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = URL.createObjectURL(file)

  try {
    const res = await tempUpload(file)
    imagePath.value = res.path
    ElMessage.success('图片已就绪')
  } catch {
    ElMessage.error('图片上传失败')
    previewUrl.value = ''
  }
}

const clearPreview = () => {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
  imagePath.value = ''
  if (fileInput.value) fileInput.value.value = ''
}

const doMatch = async () => {
  const payload = { target_type: targetType.value }
  if (imagePath.value) payload.image_path = imagePath.value
  if (text.value.trim()) payload.text = text.value.trim()
  if (!payload.image_path && !payload.text) {
    ElMessage.warning('请上传图片或输入文字描述')
    return
  }

  matching.value = true
  searched.value = true
  try {
    const res = await matchItems(payload)
    results.value = res.matches || []
    if (results.value.length === 0) {
      ElMessage.info('未找到匹配物品')
    }
  } catch (error) {
    const status = error.response?.status
    if (status === 404) {
      ElMessage.error('图片已过期，请重新上传')
      clearPreview()
    } else {
      ElMessage.error('匹配失败，请重试')
    }
  } finally {
    matching.value = false
    if (imagePath.value) clearPreview()
  }
}
</script>

<style scoped>
.match-panel {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-xl);
  padding: var(--space-8);
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
  max-width: 640px;
  margin: 0 auto var(--space-10);
  box-shadow: var(--shadow-sm);
}

.panel-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.panel-label {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}

.upload-area {
  border: 2px dashed var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--space-8);
  text-align: center;
  cursor: pointer;
  transition: all var(--transition-base);
  position: relative;
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

.upload-text { font-size: var(--text-md); color: var(--text-primary); font-weight: 500; }
.upload-hint { font-size: var(--text-sm); color: var(--text-muted); }
.upload-preview { max-width: 100%; max-height: 200px; object-fit: contain; border-radius: var(--radius-md); }
.upload-overlay { margin-top: var(--space-3); }

.match-btn {
  height: 48px;
  font-size: var(--text-lg);
  font-weight: 600;
  letter-spacing: 0.02em;
  border-radius: var(--radius-md);
}

/* ---- 结果 ---- */
.results-section {
  margin-top: var(--space-10);
}

.results-heading {
  font-size: var(--text-2xl);
  font-weight: 700;
  margin: 0 0 var(--space-5);
  color: var(--text-primary);
}

.result-count {
  font-weight: 400;
  color: var(--text-tertiary);
  font-size: var(--text-lg);
  margin-left: var(--space-3);
}

.result-card {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  overflow: hidden;
  cursor: pointer;
  border: 1px solid var(--border-light);
  box-shadow: var(--shadow-xs);
  transition: all var(--transition-slow);
}

.result-card:hover {
  box-shadow: var(--shadow-lg);
  transform: translateY(-4px);
  border-color: var(--border-default);
}

.result-card .card-img {
  width: 100%;
  aspect-ratio: 4/3;
  background: var(--neutral-100);
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
}

.result-card .card-img img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.similarity-badge {
  position: absolute;
  top: var(--space-3);
  right: var(--space-3);
  background: rgba(27, 77, 62, 0.88);
  backdrop-filter: blur(8px);
  color: white;
  padding: 3px 12px;
  border-radius: var(--radius-full);
  font-size: var(--text-sm);
  font-weight: 700;
}

.result-card .card-body {
  padding: var(--space-4);
}

.result-card .card-title {
  font-size: var(--text-lg);
  font-weight: 600;
  margin: 0 0 var(--space-1);
}

.result-card .card-desc {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0 0 var(--space-3);
  line-height: 1.5;
}

.card-meta {
  display: flex;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}

.meta-cat {
  font-size: var(--text-xs);
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  padding: 2px 10px;
  border-radius: var(--radius-full);
  font-weight: 500;
}

.similarity-bar {
  width: 100%;
}

.similarity-track {
  height: 5px;
  background: var(--neutral-200);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.similarity-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--el-color-primary-light-3), var(--el-color-primary));
  border-radius: var(--radius-full);
  transition: width 0.8s var(--transition-spring);
}

@media (max-width: 640px) {
  .match-panel {
    padding: var(--space-5);
    border-radius: var(--radius-lg);
  }
  .upload-area {
    padding: var(--space-5);
    min-height: 100px;
  }
}
</style>
