<template>
  <div class="page-container">
    <h1 class="page-title">智能匹配</h1>
    <p class="page-desc">上传图片或输入文字描述，系统将综合图像、分类、位置、时效多维匹配</p>

    <div class="match-panel">
      <!-- 目标类型 -->
      <div class="panel-section">
        <label class="panel-label">匹配目标</label>
        <el-radio-group v-model="targetType" size="large">
          <el-radio-button value="found">
            <el-icon><Search /></el-icon> 拾物（招领）
          </el-radio-button>
          <el-radio-button value="lost">
            <el-icon><Search /></el-icon> 失物
          </el-radio-button>
        </el-radio-group>
        <p class="panel-hint">{{ targetType === 'found' ? '在拾物中寻找与您的失物相似的物品' : '在失物中寻找与您的拾物相似的物品' }}</p>
      </div>

      <!-- 图片上传 -->
      <div class="panel-section">
        <label class="panel-label">上传图片 <span class="label-badge">图像匹配</span></label>
        <div class="upload-area" @click="triggerUpload">
          <input ref="fileInput" type="file" accept=".jpg,.jpeg,.png,.gif,.webp" @change="handleFileSelected" style="display:none" />
          <template v-if="previewUrl">
            <img :src="previewUrl" class="upload-preview" />
            <div class="upload-overlay">
              <el-button text type="primary" @click.stop="triggerUpload" size="small">重新选择</el-button>
              <el-button text type="danger" @click.stop="clearPreview" size="small">移除图片</el-button>
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
        <label class="panel-label">文字描述 <span class="label-badge">文本匹配</span></label>
        <el-input v-model="text" type="textarea" :rows="3" placeholder="描述物品特征，例如：黑色双肩包、带有红色挂件的钥匙串..." maxlength="300" show-word-limit />
      </div>

      <!-- 匹配按钮 -->
      <el-button type="primary" size="large" :loading="matching" @click="doMatch" :disabled="!imagePath && !text.trim()" class="match-btn">
        <el-icon><Connection /></el-icon>
        {{ matching ? 'AI 匹配中...' : '开始智能匹配' }}
      </el-button>
    </div>

    <!-- 匹配结果 -->
    <div v-if="results.length" class="results-section">
      <div class="results-head">
        <h2 class="results-heading">匹配结果 <span class="result-count">{{ results.length }} 条</span></h2>
        <div class="results-legend">
          <span class="legend-item high">≥75% 高置信</span>
          <span class="legend-item mid">≥50% 中等</span>
          <span class="legend-item low">&lt;50% 参考</span>
        </div>
      </div>

      <div class="card-grid">
        <div v-for="r in results" :key="r.id" class="result-card" @click="$router.push(`/items/${r.id}`)">
          <div class="card-img">
            <img v-if="r.image_path" :src="getImageUrl(r.image_path)" :alt="r.title" />
            <div v-else class="img-placeholder"><el-icon :size="32"><PictureFilled /></el-icon></div>
            <div class="similarity-badge" :class="badgeClass(r.similarity)">
              {{ (r.similarity * 100).toFixed(0) }}%
            </div>
          </div>
          <div class="card-body">
            <h3 class="card-title">{{ r.title }}</h3>
            <p class="card-desc" v-if="r.description">{{ r.description?.substring(0, 80) }}{{ r.description?.length > 80 ? '...' : '' }}</p>
            <div class="card-tags">
              <span class="meta-cat" v-if="r.category">{{ r.category }}</span>
              <span class="meta-loc" v-if="r.location">
                <el-icon :size="12"><LocationFilled /></el-icon>{{ r.location }}
              </span>
            </div>
            <div class="similarity-bar">
              <div class="similarity-track">
                <div class="similarity-fill" :class="badgeClass(r.similarity)" :style="{ width: (r.similarity * 100) + '%' }"></div>
              </div>
              <span class="similarity-text" :class="badgeClass(r.similarity)">{{ (r.similarity * 100).toFixed(1) }}%</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 空结果 -->
    <el-empty v-if="searched && !results.length" description="未找到匹配物品">
      <template #extra>
        <div class="empty-hints">
          <p><el-icon><Opportunity /></el-icon> 试试以下调整：</p>
          <ul>
            <li>确保目标类型选择正确（失物↔拾物交叉匹配）</li>
            <li>同时提供图片和文字描述可提高匹配精度</li>
            <li>调整描述关键词，例如颜色、品牌、特征标记</li>
          </ul>
        </div>
      </template>
    </el-empty>
  </div>
</template>

<script setup>
import { ref, onUnmounted } from 'vue'
import { matchItems, tempUpload } from '@/api/items'
import { getImageUrl } from '@/utils/helpers'
import { ElMessage } from 'element-plus'
import { Search, UploadFilled, Connection, PictureFilled, LocationFilled, Opportunity } from '@element-plus/icons-vue'

const text = ref('')
const targetType = ref('found')
const imagePath = ref('')
const previewUrl = ref('')
const fileInput = ref(null)
const results = ref([])
const matching = ref(false)
const searched = ref(false)

const badgeClass = (sim) => sim >= 0.75 ? 'high' : sim >= 0.5 ? 'mid' : 'low'

const triggerUpload = () => { fileInput.value?.click() }

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

onUnmounted(() => { if (previewUrl.value) URL.revokeObjectURL(previewUrl.value) })

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
    if (results.value.length === 0) ElMessage.info('未找到匹配物品')
  } catch (error) {
    if (error.response?.status === 404) { ElMessage.error('图片已过期，请重新上传'); clearPreview() }
    else ElMessage.error('匹配失败，请重试')
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

.panel-section { display: flex; flex-direction: column; gap: var(--space-3); }

.panel-label {
  font-size: var(--text-base); font-weight: 600; color: var(--text-primary);
  letter-spacing: -0.01em; display: flex; align-items: center; gap: var(--space-2);
}

.label-badge {
  font-size: var(--text-xs); font-weight: 500;
  padding: 1px 8px; border-radius: var(--radius-full);
  background: var(--el-color-primary-light-9); color: var(--el-color-primary);
}

.panel-hint {
  font-size: var(--text-sm); color: var(--text-tertiary); margin: 0;
}

.upload-area {
  border: 2px dashed var(--border-default); border-radius: var(--radius-lg);
  padding: var(--space-8); text-align: center; cursor: pointer;
  transition: all var(--transition-base); min-height: 140px;
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; gap: var(--space-2); background: var(--neutral-50);
}
.upload-area:hover { border-color: var(--el-color-primary); background: var(--el-color-primary-light-9); }
.upload-text { font-size: var(--text-md); color: var(--text-primary); font-weight: 500; }
.upload-hint { font-size: var(--text-sm); color: var(--text-muted); }
.upload-preview { max-width: 100%; max-height: 200px; object-fit: contain; border-radius: var(--radius-md); }
.upload-overlay { margin-top: var(--space-3); }

.match-btn {
  height: 48px; font-size: var(--text-lg); font-weight: 600;
  letter-spacing: 0.02em; border-radius: var(--radius-md);
}

/* ---- 结果 ---- */
.results-section { margin-top: var(--space-10); }

.results-head {
  display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: var(--space-2); margin-bottom: var(--space-5);
}
.results-heading { font-size: var(--text-2xl); font-weight: 700; margin: 0; color: var(--text-primary); }
.result-count { font-weight: 400; color: var(--text-tertiary); font-size: var(--text-lg); margin-left: var(--space-3); }

.results-legend { display: flex; gap: var(--space-3); }
.legend-item { font-size: var(--text-xs); padding: 1px 8px; border-radius: var(--radius-full); }
.legend-item.high { background: #E8F5E9; color: #2E7D32; }
.legend-item.mid { background: #FFF3E0; color: #E65100; }
.legend-item.low { background: var(--neutral-100); color: var(--text-tertiary); }

/* ---- 卡片 ---- */
.result-card {
  background: var(--bg-card); border-radius: var(--radius-lg); overflow: hidden;
  cursor: pointer; border: 1px solid var(--border-light);
  box-shadow: var(--shadow-xs); transition: all var(--transition-slow);
}
.result-card:hover { box-shadow: var(--shadow-lg); transform: translateY(-4px); border-color: var(--border-default); }

.result-card .card-img {
  width: 100%; aspect-ratio: 4/3; background: var(--neutral-100);
  display: flex; align-items: center; justify-content: center;
  position: relative; overflow: hidden;
}
.result-card .card-img img { width: 100%; height: 100%; object-fit: cover; }

.similarity-badge {
  position: absolute; top: var(--space-3); right: var(--space-3);
  padding: 3px 12px; border-radius: var(--radius-full);
  font-size: var(--text-sm); font-weight: 700; backdrop-filter: blur(8px);
}
.similarity-badge.high { background: rgba(46,125,50,0.88); color: #fff; }
.similarity-badge.mid  { background: rgba(230,81,0,0.88); color: #fff; }
.similarity-badge.low  { background: rgba(0,0,0,0.55); color: #fff; }

.result-card .card-body { padding: var(--space-4); }
.result-card .card-title { font-size: var(--text-lg); font-weight: 600; margin: 0 0 var(--space-1); }
.result-card .card-desc { font-size: var(--text-sm); color: var(--text-secondary); margin: 0 0 var(--space-3); line-height: 1.5; }

.card-tags { display: flex; gap: var(--space-2); flex-wrap: wrap; margin-bottom: var(--space-3); }
.meta-cat {
  font-size: var(--text-xs); color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  padding: 2px 10px; border-radius: var(--radius-full); font-weight: 500;
}
.meta-loc {
  font-size: var(--text-xs); color: var(--text-tertiary);
  display: flex; align-items: center; gap: 2px;
}

.similarity-bar { display: flex; align-items: center; gap: 8px; }
.similarity-track { flex: 1; height: 5px; background: var(--neutral-200); border-radius: var(--radius-full); overflow: hidden; }
.similarity-fill { height: 100%; border-radius: var(--radius-full); transition: width 0.8s var(--transition-spring); }
.similarity-fill.high { background: linear-gradient(90deg, #4CAF50, #66BB6A); }
.similarity-fill.mid  { background: linear-gradient(90deg, #FF9800, #FFA726); }
.similarity-fill.low  { background: linear-gradient(90deg, #9E9E9E, #BDBDBD); }
.similarity-text { font-size: var(--text-sm); font-weight: 600; white-space: nowrap; }
.similarity-text.high { color: #2E7D32; }
.similarity-text.mid  { color: #E65100; }
.similarity-text.low  { color: var(--text-muted); }

/* ---- 空状态 ---- */
.empty-hints { text-align: left; max-width: 400px; margin: 0 auto; }
.empty-hints p { margin-bottom: var(--space-2); font-weight: 500; }
.empty-hints ul { margin: 0; padding-left: var(--space-5); font-size: var(--text-sm); color: var(--text-secondary); }
.empty-hints li { margin-bottom: var(--space-1); }

@media (max-width: 640px) {
  .match-panel { padding: var(--space-5); border-radius: var(--radius-lg); }
  .upload-area { padding: var(--space-5); min-height: 100px; }
}
</style>
