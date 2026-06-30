<template>
  <div class="page-container">
    <div class="page-header">
      <div>
        <h1 class="page-title">发现物品</h1>
        <p class="page-desc">浏览所有已发布的失物与拾物信息</p>
      </div>
      <el-button type="primary" @click="$router.push('/publish')" class="publish-cta">
        <el-icon><Plus /></el-icon>发布物品
      </el-button>
    </div>

    <!-- v3.3: 数据看板（总计找回替代今日找回） -->
    <div class="stats-row" v-if="stats">
      <div class="stat-card">
        <span class="stat-num">{{ stats.active_count || 0 }}</span>
        <span class="stat-label">展示中</span>
      </div>
      <div class="stat-card stat-lost">
        <span class="stat-num">{{ stats.today_lost || 0 }}</span>
        <span class="stat-label">今日失物</span>
      </div>
      <div class="stat-card stat-found">
        <span class="stat-num">{{ stats.today_found || 0 }}</span>
        <span class="stat-label">今日拾物</span>
      </div>
      <div class="stat-card stat-claimed">
        <span class="stat-num">{{ stats.total_claimed || 0 }}</span>
        <span class="stat-label">🏆 总计找回</span>
      </div>
    </div>

    <!-- 公告栏 -->
    <div class="announce-bar" v-if="announcements.length">
      <div v-for="a in announcements" :key="a.id" class="announce-item" :class="{ pinned: a.is_pinned }">
        <el-icon :size="16"><Bell /></el-icon>
        <span class="announce-title">{{ a.title }}</span>
        <span class="announce-content">{{ a.content?.substring(0, 80) }}{{ a.content?.length > 80 ? '...' : '' }}</span>
        <span class="announce-time">{{ a.created_at }}</span>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <el-radio-group v-model="filters.type" @change="loadItems" size="default">
        <el-radio-button value="">全部</el-radio-button>
        <el-radio-button value="lost">失物</el-radio-button>
        <el-radio-button value="found">拾物</el-radio-button>
      </el-radio-group>
      <div class="filter-right">
        <el-select v-model="filters.category" placeholder="全部分类" clearable @change="loadItems" style="width:150px">
          <el-option label="全部分类" value="" />
          <el-option v-for="cat in categories" :key="cat" :label="cat" :value="cat" />
        </el-select>
        <el-input
          v-model="filters.keyword"
          placeholder="搜索关键词..."
          clearable
          :prefix-icon="Search"
          @keyup.enter="loadItems"
          @clear="loadItems"
          style="width:200px"
        />
        <el-checkbox v-model="showMine" @change="loadItems" class="mine-checkbox">
          仅显示我的
        </el-checkbox>
      </div>
    </div>

    <!-- 骨架屏加载 -->
    <div v-if="loading" class="card-grid">
      <SkeletonCard v-for="i in 6" :key="i" />
    </div>

    <!-- 空状态 -->
    <el-empty v-else-if="items.length === 0" description="暂无物品，去发布第一条吧">
      <el-button type="primary" @click="$router.push('/publish')">发布物品</el-button>
    </el-empty>

    <!-- 物品卡片网格 -->
    <div v-else class="card-grid">
      <div
        v-for="item in items"
        :key="item.id"
        class="item-card"
        @click="$router.push(`/items/${item.id}`)"
      >
        <div class="card-img">
          <img
            v-if="item.image_path"
            :src="getImageUrl(item.image_path)"
            :alt="item.title"
            @error="handleImgError"
            loading="lazy"
          />
          <div v-else class="img-placeholder">
            <el-icon :size="36"><PictureFilled /></el-icon>
            <span>暂无图片</span>
          </div>
          <span
            class="type-badge"
            :style="{ background: ITEM_TYPE_MAP[item.type]?.bg, color: ITEM_TYPE_MAP[item.type]?.color }"
          >
            {{ ITEM_TYPE_MAP[item.type]?.label }}
          </span>
        </div>
        <div class="card-body">
          <h3 class="card-title">{{ item.title }}</h3>
          <p class="card-desc" v-if="item.description">{{ truncate(item.description, 60) }}</p>
          <div class="card-meta">
            <span class="meta-item" v-if="item.category">
              <el-icon :size="14"><Folder /></el-icon>
              {{ item.category }}
            </span>
            <span class="meta-item" v-if="item.location">
              <el-icon :size="14"><LocationFilled /></el-icon>
              {{ item.location }}
            </span>
          </div>
          <div class="card-footer">
            <span class="card-time">{{ item.created_at }}</span>
            <span
              v-if="item.review_status"
              class="status-tag"
              :style="{ background: REVIEW_STATUS_MAP[item.review_status]?.bg, color: REVIEW_STATUS_MAP[item.review_status]?.color }"
            >
              {{ REVIEW_STATUS_MAP[item.review_status]?.label }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- 分页 -->
    <div v-if="total > pageSize" class="pagination-wrap">
      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="prev, pager, next"
        @current-change="loadItems"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { getItems, getCategories } from '@/api/items'
import { getImageUrl, ITEM_TYPE_MAP, REVIEW_STATUS_MAP, truncate } from '@/utils/helpers'
import { Search, PictureFilled, Folder, LocationFilled, Plus } from '@element-plus/icons-vue'
import SkeletonCard from '@/components/SkeletonCard.vue'
import request from '@/utils/request'
import { getAnnouncements } from '@/api/announcements'
import { Bell } from '@element-plus/icons-vue'

const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const filters = ref({ type: '', category: '', keyword: '' })
const categories = ref([])
const showMine = ref(false)
const stats = ref(null)
const announcements = ref([])

const authStore = useAuthStore()

const loadItems = async () => {
  loading.value = true
  try {
    const params = {
      ...filters.value,
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value
    }
    Object.keys(params).forEach(k => {
      if (params[k] === '') delete params[k]
    })
    if (showMine.value && authStore.user?.id) {
      params.user_id = authStore.user.id
    }
    const res = await getItems(params)
    items.value = res.items || []
    total.value = res.total || 0
  } catch (e) {
    console.error('加载物品列表失败', e)
  } finally {
    loading.value = false
  }
}

const handleImgError = (e) => {
  e.target.style.display = 'none'
}

const loadStats = async () => {
  try {
    const res = await request.get('/stats/dashboard')
    // v3.3: 响应格式 { success, data: { active_count, today_lost, today_found, total_claimed } }
    // axios 拦截器已解包 response.data → res = { success, data: { ... } }
    const d = res.data || res
    stats.value = {
      active_count: d.active_count ?? 0,
      today_lost: d.today_lost ?? 0,
      today_found: d.today_found ?? 0,
      total_claimed: d.total_claimed ?? 0
    }
  } catch (e) {
    console.error('加载统计数据失败:', e)
    stats.value = null  // 不展示统计卡片而非展示错误数据
  }
}

const loadAnnouncements = async () => {
  try { const res = await getAnnouncements(); announcements.value = res.announcements || [] } catch { }
}

onMounted(() => {
  getCategories().then(res => { categories.value = res.categories || [] }).catch(() => {})
  loadItems()
  loadStats()
  loadAnnouncements()
})
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
  flex-wrap: wrap;
  margin-bottom: var(--space-5);
}

.page-header .page-title {
  margin-bottom: var(--space-1);
}

.publish-cta {
  flex-shrink: 0;
  font-weight: 600;
}

/* ---- 公告栏 ---- */
.announce-bar {
  margin-bottom: var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.announce-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.announce-item.pinned {
  background: #FFF8E1;
  border-color: #FFE082;
}

.announce-title {
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
}

.announce-content {
  flex: 1;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.announce-time {
  font-size: var(--text-xs);
  color: var(--text-muted);
  white-space: nowrap;
}

/* ---- 数据看板 ---- */
.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-4);
  margin-bottom: var(--space-5);
}

.stat-card {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: var(--space-4) var(--space-5);
  text-align: center;
  box-shadow: var(--shadow-xs);
}

.stat-num {
  display: block;
  font-size: var(--text-4xl);
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1;
}

.stat-label {
  display: block;
  font-size: var(--text-sm);
  color: var(--text-tertiary);
  margin-top: var(--space-1);
}

.stat-lost .stat-num { color: #E57373; }
.stat-found .stat-num { color: #66BB6A; }
.stat-claimed .stat-num { color: var(--el-color-primary); }

@media (max-width: 640px) {
  .stats-row {
    grid-template-columns: repeat(2, 1fr);
  }
}

/* ---- 筛选栏 ---- */
.filter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  flex-wrap: wrap;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  margin-bottom: var(--space-6);
}

.filter-right {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.mine-checkbox {
  white-space: nowrap;
}

/* ---- 物品卡片 ---- */
.item-card {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  overflow: hidden;
  cursor: pointer;
  border: 1px solid var(--border-light);
  box-shadow: var(--shadow-xs);
  transition: all var(--transition-slow);
}

.item-card:hover {
  box-shadow: var(--shadow-lg);
  transform: translateY(-4px);
  border-color: var(--border-default);
}

.card-img {
  width: 100%;
  aspect-ratio: 4 / 3;
  position: relative;
  overflow: hidden;
  background: var(--neutral-100);
}

.card-img img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform var(--transition-slow);
}

.item-card:hover .card-img img {
  transform: scale(1.04);
}

.card-body {
  padding: var(--space-4);
}

.card-title {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 var(--space-2);
  line-height: 1.3;
}

.card-desc {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0 0 var(--space-3);
  line-height: 1.5;
}

.card-meta {
  display: flex;
  gap: var(--space-4);
  flex-wrap: wrap;
  margin-bottom: var(--space-3);
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: var(--space-3);
  border-top: 1px solid var(--border-light);
}

.card-time {
  font-size: var(--text-sm);
  color: var(--text-muted);
}

.pagination-wrap {
  display: flex;
  justify-content: center;
  margin-top: var(--space-8);
}

/* ---- 响应式 ---- */
@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    gap: var(--space-3);
  }

  .publish-cta {
    width: 100%;
  }

  .filter-bar {
    flex-direction: column;
    align-items: stretch;
  }

  .filter-right {
    flex-direction: column;
    align-items: stretch;
  }

  .filter-right > * {
    width: 100%;
  }
}
</style>
