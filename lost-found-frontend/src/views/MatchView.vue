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

      <!-- 图片上传（v3.6.0：1-3 张多图综合评分） -->
      <div class="panel-section">
        <label class="panel-label">上传图片 <span class="label-badge">图像匹配</span></label>
        <div class="upload-area" @click="triggerUpload">
          <input ref="fileInput" type="file" accept=".jpg,.jpeg,.png,.gif,.webp" @change="handleFileSelected" style="display:none" />
          <template v-if="uploadedImages.length">
            <div class="preview-row">
              <div v-for="(img, i) in uploadedImages" :key="img.path" class="preview-item">
                <img :src="img.previewUrl" class="upload-preview" />
                <span class="preview-index">{{ i + 1 }}</span>
                <el-button class="preview-remove" circle size="small" type="danger" @click.stop="removeImage(i)">
                  <el-icon><Close /></el-icon>
                </el-button>
              </div>
              <div v-if="uploadedImages.length < 3" class="preview-add" @click.stop="triggerUpload">
                <el-icon :size="20"><Plus /></el-icon>
              </div>
            </div>
            <div class="upload-overlay">
              <span class="upload-hint">已选 {{ uploadedImages.length }}/3 张，建议上传同一物品的不同角度（最多 3 张综合评分）</span>
            </div>
          </template>
          <template v-else>
            <el-icon :size="40"><UploadFilled /></el-icon>
            <span class="upload-text">点击上传图片（最多 3 张）</span>
            <span class="upload-hint">支持 JPG、PNG、GIF、WebP；多图将综合评分</span>
          </template>
        </div>
      </div>

      <!-- 文字描述 -->
      <div class="panel-section">
        <label class="panel-label">文字描述 <span class="label-badge">文本匹配</span></label>
        <el-input v-model="text" type="textarea" :rows="3" placeholder="用一句话描述物品，例如：黑色皮质长款钱包，正面有金属拉链和圆形徽章，里面夹着校园卡..." maxlength="300" show-word-limit />
        <p class="panel-hint">建议用完整自然语言描述；把最关键的特征（颜色 / 品牌 / 特殊标记）写在前 {{ TEXT_TOWER_WINDOW }} 字内，识别更准。</p>
        <p v-if="textCharCount > TEXT_TOWER_WINDOW" class="panel-hint panel-hint-warn">
          <el-icon><WarningFilled /></el-icon>
          <span>已输入 {{ textCharCount }} 字：超出 {{ TEXT_TOWER_WINDOW }} 字的部分不影响匹配精度，建议把关键特征写在前 {{ TEXT_TOWER_WINDOW }} 字内。</span>
        </p>
      </div>

      <!-- 类别与位置（可选，提升匹配精度） -->
      <div class="panel-section">
        <label class="panel-label">类别与位置 <span class="label-badge">可选</span></label>
        <div class="form-row">
          <el-select v-model="category" placeholder="选择类别" clearable style="flex:1" size="large">
            <el-option v-for="cat in categories" :key="cat" :label="cat" :value="cat" />
          </el-select>
          <el-input v-model="location" placeholder="丢失或发现地点" clearable style="flex:1" size="large">
            <template #prefix><el-icon><LocationFilled /></el-icon></template>
          </el-input>
        </div>
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
          <span class="legend-item high">≥{{ (legend.high * 100).toFixed(0) }}% 高置信</span>
          <span class="legend-item mid">≥{{ (legend.mid * 100).toFixed(0) }}% 中等</span>
          <span class="legend-item low">&lt;{{ (legend.mid * 100).toFixed(0) }}% 参考</span>
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
            <!-- v3.6.0：证据等级徽章 -->
            <div v-if="r.level" class="evidence-badge" :style="{ background: evidenceColor(r.level) }">
              {{ EVIDENCE_LEVEL_MAP[r.level]?.label || r.level }}
            </div>
          </div>
          <div class="card-body">
            <h3 class="card-title">{{ r.title }}</h3>
            <p class="card-desc" v-if="r.description">{{ r.description?.substring(0, 80) }}{{ r.description?.length > 80 ? '...' : '' }}</p>
            <div class="card-tags">
              <span class="meta-src" :class="'src-' + (r.match_source || 'mixed')">{{ matchSourceLabel(r.match_source) }}</span>
              <span class="meta-cat" v-if="r.category">{{ r.category }}</span>
              <span class="meta-loc" v-if="r.location">
                <el-icon :size="12"><LocationFilled /></el-icon>{{ r.location }}
              </span>
            </div>
            <!-- v3.6.0：命中依据（证据链可解释性） -->
            <p v-if="basisToText(r.basis)" class="evidence-basis">
              <el-icon :size="12"><DocumentChecked /></el-icon>{{ basisToText(r.basis) }}
            </p>
            <div class="similarity-bar">
              <div class="similarity-track">
                <div class="similarity-fill" :class="badgeClass(r.similarity)" :style="{ width: (r.similarity * 100) + '%' }"></div>
              </div>
              <span class="similarity-text" :class="badgeClass(r.similarity)">{{ (r.similarity * 100).toFixed(1) }}%</span>
            </div>
            <p class="similarity-note">相似度由 AI 估算，仅供参考</p>
          </div>
        </div>
      </div>
    </div>

    <!-- 空结果 -->
    <el-empty v-if="searched && !results.length" description="暂未找到相似的物品">
      <template #extra>
        <div class="empty-hints">
          <p><el-icon><Opportunity /></el-icon> 可以这样再试试：</p>
          <ul>
            <li>用一句自然语言完整描述，例如「黑色皮质长款钱包，正面有金属拉链」</li>
            <li>把最关键的特征（颜色 / 品牌 / 特殊标记）写在前 50 字内</li>
            <li>同时上传图片并补充文字描述，命中率更高</li>
            <li>确认目标类型是否正确（失物 ↔ 拾物交叉匹配）</li>
            <li>相似度由 AI 估算，结果仅供参考，请结合实物核对</li>
          </ul>
        </div>
      </template>
    </el-empty>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { matchItems, tempUpload, getCategories } from '@/api/items'
import { getImageUrl, EVIDENCE_LEVEL_MAP, basisToText } from '@/utils/helpers'
import { ElMessage } from 'element-plus'
import { Search, UploadFilled, Connection, PictureFilled, LocationFilled, Opportunity, WarningFilled, Plus, Close, DocumentChecked } from '@element-plus/icons-vue'

// 图例本地回落常量：后端未升级（无 legend）时保证不炸
const LEGEND_FALLBACK = { high: 0.75, mid: 0.5 }

// 模型文本塔可用窗口（汉字）：context_length 52 − [CLS] − [SEP] = 50。
// 超长输入会被**静默截断**，故仅提示、绝不拦截/截断用户输入。
const TEXT_TOWER_WINDOW = 50

// v3.6.0：多图上限（与后端 image_paths ≤3 一致）
const MAX_IMAGES = 3

const route = useRoute()
const text = ref('')
const targetType = ref('found')
const category = ref('')
const location = ref('')
const categories = ref([])
// v3.6.0：多图 [{ path: 临时文件名, previewUrl: 本地预览 }]
const uploadedImages = ref([])
const fileInput = ref(null)
const results = ref([])
const matching = ref(false)
const searched = ref(false)
const legend = ref({ ...LEGEND_FALLBACK })
let autoRan = false

// 已输入字符数（与 el-input show-word-limit / 模型窗口同口径：中文一字一字符）
const textCharCount = computed(() => (text.value || '').length)

const matchSourceLabel = (src) => (
  src === 'image' ? '按图匹配'
    : src === 'text' ? '按描述匹配'
      : '图文混合'
)

const badgeClass = (sim) => sim >= legend.value.high ? 'high' : sim >= legend.value.mid ? 'mid' : 'low'

const evidenceColor = (level) => EVIDENCE_LEVEL_MAP[level]?.color || '#9E9E9E'

const triggerUpload = () => { fileInput.value?.click() }

const handleFileSelected = async (e) => {
  const file = e.target.files[0]
  if (!file) return
  if (uploadedImages.value.length >= MAX_IMAGES) {
    ElMessage.warning(`最多上传 ${MAX_IMAGES} 张图片`)
    return
  }
  const previewUrl = URL.createObjectURL(file)
  try {
    const res = await tempUpload(file)
    uploadedImages.value.push({ path: res.path, previewUrl })
    ElMessage.success(`图片 ${uploadedImages.value.length}/${MAX_IMAGES} 已就绪`)
  } catch {
    URL.revokeObjectURL(previewUrl)
    ElMessage.error('图片上传失败')
  } finally {
    if (fileInput.value) fileInput.value.value = ''
  }
}

const removeImage = (index) => {
  const [removed] = uploadedImages.value.splice(index, 1)
  if (removed?.previewUrl) URL.revokeObjectURL(removed.previewUrl)
}

const clearAllImages = () => {
  uploadedImages.value.forEach((img) => URL.revokeObjectURL(img.previewUrl))
  uploadedImages.value = []
  if (fileInput.value) fileInput.value.value = ''
}

onMounted(() => {
  getCategories().then(res => { categories.value = res.categories || [] }).catch(() => {})
  // 支持首页 /match?text=... 直达：预填并**显式执行一次**匹配（不做输入即搜）
  const q = route.query.text
  if (typeof q === 'string' && q.trim() && !autoRan) {
    autoRan = true
    text.value = q.trim()
    doMatch()
  }
})
onUnmounted(clearAllImages)

const doMatch = async () => {
  const payload = { target_type: targetType.value }
  const paths = uploadedImages.value.map((i) => i.path)
  if (paths.length > 1) payload.image_paths = paths
  else if (paths.length === 1) payload.image_path = paths[0]
  if (text.value.trim()) payload.text = text.value.trim()
  if (category.value) payload.category = category.value
  if (location.value) payload.location = location.value
  if (!payload.image_path && !payload.image_paths && !payload.text) {
    ElMessage.warning('请上传图片或输入文字描述')
    return
  }
  matching.value = true
  searched.value = true
  try {
    const res = await matchItems(payload)
    results.value = res.matches || []
    // 图例以后端 legend 为单一数据源；缺失时回落本地常量（后端未升级也不炸）
    if (res.legend && typeof res.legend === 'object') {
      legend.value = {
        high: typeof res.legend.high === 'number' ? res.legend.high : LEGEND_FALLBACK.high,
        mid: typeof res.legend.mid === 'number' ? res.legend.mid : LEGEND_FALLBACK.mid
      }
    } else {
      legend.value = { ...LEGEND_FALLBACK }
    }
    if (results.value.length === 0) ElMessage.info('未找到匹配物品')
  } catch (error) {
    if (error.response?.status === 404) { ElMessage.error('图片已过期，请重新上传'); clearAllImages() }
    else ElMessage.error('匹配失败，请重试')
  } finally {
    matching.value = false
    // 临时图在匹配后被后端删除，本地状态一并清空
    if (uploadedImages.value.length) clearAllImages()
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

.panel-hint-warn {
  display: flex; align-items: center; gap: var(--space-1);
  color: #E65100;
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

/* v3.6.0：多图预览行 */
.preview-row {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
}

.preview-item {
  position: relative;
  width: 120px;
  height: 120px;
  border-radius: var(--radius-md);
  overflow: hidden;
  border: 1px solid var(--border-default);
}

.preview-item .upload-preview {
  width: 100%;
  height: 100%;
  object-fit: cover;
  max-height: none;
}

.preview-index {
  position: absolute;
  top: 4px;
  left: 4px;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  font-size: 11px;
  padding: 1px 7px;
  border-radius: var(--radius-full);
}

.preview-remove {
  position: absolute;
  top: 4px;
  right: 4px;
}

.preview-add {
  width: 120px;
  height: 120px;
  border: 2px dashed var(--border-default);
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  cursor: pointer;
  transition: all var(--transition-base);
}
.preview-add:hover { border-color: var(--el-color-primary); color: var(--el-color-primary); }

/* v3.6.0：证据等级徽章与依据文案 */
.evidence-badge {
  position: absolute;
  top: var(--space-3);
  left: var(--space-3);
  padding: 2px 10px;
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: 600;
  color: #fff;
}

.evidence-basis {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: var(--text-xs);
  color: var(--text-secondary);
  margin: 0 0 var(--space-2);
  line-height: 1.5;
}

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
.meta-src {
  font-size: var(--text-xs); font-weight: 500;
  padding: 2px 10px; border-radius: var(--radius-full);
  background: var(--neutral-100); color: var(--text-secondary);
}
.meta-src.src-image { background: #E3F2FD; color: #1565C0; }
.meta-src.src-text  { background: #F3E5F5; color: #6A1B9A; }
.meta-src.src-mixed { background: #E8F5E9; color: #2E7D32; }

.similarity-note {
  font-size: var(--text-xs); color: var(--text-muted);
  margin: var(--space-2) 0 0; text-align: right;
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

.form-row {
  display: flex; gap: var(--space-3); align-items: center;
}

@media (max-width: 640px) {
  .match-panel { padding: var(--space-5); border-radius: var(--radius-lg); }
  .upload-area { padding: var(--space-5); min-height: 100px; }
  .form-row { flex-direction: column; }
}
</style>
