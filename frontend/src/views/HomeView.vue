<template>
  <div class="page-container">
    <!-- 首页为纯展示页：无标题与发布按钮；大厅保留标题与发布入口 -->
    <div class="page-header" v-if="hallType">
      <div>
        <h1 class="page-title">{{ hallType === 'lost' ? '失物大厅' : '招领大厅' }}</h1>
        <p class="page-desc">{{ hallType === 'lost' ? '浏览所有已发布的失物信息' : '浏览所有已发布的拾物信息' }}</p>
      </div>
      <el-button type="primary" @click="$router.push('/publish')" class="publish-cta">
        <el-icon><Plus /></el-icon>发布物品
      </el-button>
    </div>

    <!-- v3.6.0：轮播图（管理员运营位；首页专属，大厅不展示） -->
    <div v-if="!hallType && banners.length" class="banner-carousel">
      <el-carousel height="220px" :interval="5000" arrow="hover" indicator-position="none">
        <el-carousel-item v-for="b in banners" :key="b.id">
          <div class="banner-item" @click="bannerClick(b)">
            <img :src="getImageUrl(b.image_path)" :alt="b.title" />
            <div class="banner-caption" v-if="b.title || b.description">
              <span class="banner-title" v-if="b.title">{{ b.title }}</span>
              <span class="banner-desc" v-if="b.description">{{ b.description }}</span>
            </div>
          </div>
        </el-carousel-item>
      </el-carousel>
    </div>

    <!-- 统计卡片 + 校园公告：同一高度各占一半（首页专属） -->
    <div class="home-mid" v-if="!hallType && (stats || announcements.length)">
      <!-- 统计卡片（左半） -->
      <div class="dashboard" v-if="stats">
        <div class="dashboard-left">
          <div class="stat-grid">
            <div class="stat-item">
              <span class="stat-num">{{ stats.active_count || 0 }}</span>
              <span class="stat-label">展示中</span>
            </div>
            <div class="stat-item">
              <span class="stat-num" style="color:#E57373">{{ stats.today_lost || 0 }}</span>
              <span class="stat-label">今日失物</span>
            </div>
            <div class="stat-item">
              <span class="stat-num" style="color:#66BB6A">{{ stats.today_found || 0 }}</span>
              <span class="stat-label">今日拾物</span>
            </div>
            <div class="stat-item">
              <span class="stat-num" style="color:var(--el-color-primary)">{{ stats.total_claimed || 0 }}</span>
              <span class="stat-label">总计找回</span>
            </div>
          </div>
        </div>
        <div class="dashboard-right" v-if="stats.categories?.length >= 3">
          <div class="pie-mini" ref="pieChartRef"></div>
        </div>
      </div>

      <!-- 校园公告（右半）：置顶优先 + 最新，最多 5 条 -->
      <div class="announce-panel" v-if="announcements.length">
        <div class="announce-panel-head">
          <h2 class="announce-panel-title">校园公告</h2>
          <router-link to="/announcements" class="announce-more">查看更多 →</router-link>
        </div>
        <div class="announce-panel-list">
          <div
            v-for="a in announcements.slice(0, 5)"
            :key="a.id"
            class="announce-panel-item"
            @click="$router.push(`/announcements/${a.id}`)"
          >
            <el-tag v-if="a.is_pinned" type="warning" size="small" effect="dark">置顶</el-tag>
            <span class="announce-panel-title-text">{{ a.title }}</span>
            <span class="announce-panel-time">{{ a.created_at }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- v3.6.0：为你推荐（管理员审核时勾选的推荐位；首页专属） -->
    <div v-if="!hallType && recommends.length" class="recommend-section">
      <div class="recommend-head">
        <h2 class="recommend-title">
          <el-icon><StarFilled /></el-icon>为你推荐
        </h2>
      </div>
      <div class="recommend-grid">
        <div
          v-for="r in recommends.slice(0, 5)"
          :key="r.id"
          class="recommend-card"
          @click="$router.push(`/items/${r.id}`)"
        >
          <img v-if="r.image_path" :src="getImageUrl(r.image_path)" :alt="r.title" loading="lazy" />
          <div v-else class="img-placeholder recommend-ph">
            <el-icon :size="26"><PictureFilled /></el-icon>
            <span class="recommend-ph-title">{{ r.title }}</span>
            <span class="recommend-ph-meta">{{ ITEM_TYPE_MAP[r.type]?.label }}{{ r.category ? ' · ' + r.category : '' }}</span>
          </div>
          <div class="recommend-body" v-if="r.image_path">
            <span class="recommend-item-title">{{ r.title }}</span>
            <span class="recommend-meta">{{ ITEM_TYPE_MAP[r.type]?.label }}{{ r.category ? ' · ' + r.category : '' }}</span>
          </div>
        </div>
        <!-- 行末尾：大厅引导入口 -->
        <div class="recommend-more">
          <router-link to="/hall/lost" class="recommend-more-link">
            前往失物大厅 <el-icon :size="12"><ArrowRight /></el-icon>
          </router-link>
          <router-link to="/hall/found" class="recommend-more-link">
            前往招领大厅 <el-icon :size="12"><ArrowRight /></el-icon>
          </router-link>
        </div>
      </div>
    </div>

    <!-- 筛选栏（大厅专属；类型由路由锁定） -->
    <div class="filter-bar" v-if="hallType">
      <el-tag size="large" :type="hallType === 'lost' ? 'danger' : 'success'" effect="dark">
        {{ hallType === 'lost' ? '失物大厅' : '招领大厅' }}
      </el-tag>
      <div class="filter-right">
        <el-select v-model="filters.category" placeholder="全部分类" clearable @change="loadItems" style="width:150px">
          <el-option label="全部分类" value="" />
          <el-option v-for="cat in categories" :key="cat" :label="cat" :value="cat" />
        </el-select>
        <el-input
          v-model="filters.keyword"
          placeholder="按关键词精确搜索"
          clearable
          :prefix-icon="Search"
          @keyup.enter="loadItems"
          @clear="loadItems"
          style="width:200px"
        />
        <el-button text type="primary" class="smart-jump" @click="goSmartMatchFromKeyword">
          <el-icon><MagicStick /></el-icon>按描述智能查找 →
        </el-button>
        <el-checkbox v-model="showMine" @change="loadItems" class="mine-checkbox">
          仅显示我的
        </el-checkbox>
      </div>
    </div>

    <!-- 大厅物品列表（骨架屏 / 空状态 / 卡片网格） -->
    <template v-if="hallType">
    <div v-if="loading" class="card-grid">
      <SkeletonCard v-for="i in 6" :key="i" />
    </div>

    <el-empty v-else-if="items.length === 0" :description="`暂无${hallType === 'lost' ? '失物' : '拾物'}，去发布第一条吧`">
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
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed, nextTick, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { getItems, getCategories, getRecommend } from '@/api/items'
import { publicBanners } from '@/api/banners'
import { getImageUrl, ITEM_TYPE_MAP, REVIEW_STATUS_MAP, truncate } from '@/utils/helpers'
import { Search, PictureFilled, Folder, LocationFilled, Plus, MagicStick, StarFilled, ArrowRight } from '@element-plus/icons-vue'
import SkeletonCard from '@/components/SkeletonCard.vue'
import request from '@/utils/request'
import { getAnnouncements } from '@/api/announcements'
import * as echarts from 'echarts'

const route = useRoute()
// 大厅模式：/hall/lost、/hall/found 复用本组件，类型由路由 meta 锁定
const hallType = computed(() => route.meta.hallType || '')

const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const filters = ref({ type: hallType.value, category: '', keyword: '' })
const categories = ref([])
const showMine = ref(false)
const stats = ref(null)
const announcements = ref([])
// v3.6.0：轮播图 + 为你推荐
const banners = ref([])
const recommends = ref([])

const pieChartRef = ref(null)
let pieChart = null

const authStore = useAuthStore()
const router = useRouter()

// 防止用户把长句输进 LIKE 精确搜索框：取当前 keyword 作为描述带去 /match
const goSmartMatchFromKeyword = () => {
  const q = (filters.value.keyword || '').trim()
  router.push({ path: '/match', query: q ? { text: q } : {} })
}

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
      total_claimed: d.total_claimed ?? 0,
      categories: d.categories || []
    }
    // 渲染饼图（仅≥3分类，等DOM更新后初始化）
    await nextTick()
    if (pieChart) { pieChart.dispose(); pieChart = null }
    if (stats.value.categories.length >= 3 && pieChartRef.value) {
      pieChart = echarts.init(pieChartRef.value)
      pieChart.setOption({
        tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
        series: [{
          type: 'pie', radius: ['45%', '75%'], center: ['50%', '50%'],
          itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 3 },
          label: { show: false },
          emphasis: { label: { show: true, fontSize: 14, fontWeight: 'bold' } },
          data: stats.value.categories.map(c => ({ name: c.name, value: c.count }))
        }],
        color: ['#2C5F4F','#4CAF50','#FF9800','#2196F3','#9C27B0','#E91E63','#607D8B']
      })
    }
  } catch (e) {
    console.error('加载统计数据失败:', e)
    stats.value = null
  }
}

const loadAnnouncements = async () => {
  // 首页公告面板最多 5 条（后端已按 置顶优先 + 最新 排序）
  try {
    const res = await getAnnouncements(false, { size: 5 })
    announcements.value = res.announcements || []
  } catch { }
}

// v3.6.0：轮播图与推荐位
const loadBanners = async () => {
  try { const res = await publicBanners(); banners.value = res.banners || [] } catch { }
}
const bannerClick = (b) => {
  if (b.link_url) {
    if (b.link_url.startsWith('http')) window.open(b.link_url, '_blank')
    else router.push(b.link_url)
  }
}
const loadRecommends = async () => {
  // 首页推荐一排 5 条（最近审核通过）
  try { const res = await getRecommend({ limit: 5 }); recommends.value = res.items || [] } catch { }
}

// 大厅 ↔ 首页切换（组件复用，onMounted 不重跑）
watch(() => route.meta.hallType, (t) => {
  if (t) {
    // 进入大厅：锁定类型并重载物品列表
    filters.value.type = t
    page.value = 1
    loadItems()
  } else {
    // 从大厅返回首页：补齐轮播/统计/公告/推荐数据（否则首页空白）
    loadStats()
    loadBanners()
    loadAnnouncements()
    loadRecommends()
  }
})

onMounted(() => {
  getCategories().then(res => { categories.value = res.categories || [] }).catch(() => {})
  loadItems()
  // 轮播/统计/公告/推荐为首页专属，大厅只加载物品列表
  if (!hallType.value) {
    loadStats()
    loadAnnouncements()
    loadBanners()
    loadRecommends()
  }
})

onUnmounted(() => {
  if (pieChart) { pieChart.dispose(); pieChart = null }
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

/* ---- v3.6.0：轮播图 ---- */
.banner-carousel {
  margin-bottom: var(--space-5);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-xs);
}

.banner-item {
  width: 100%;
  height: 100%;
  position: relative;
  cursor: pointer;
}

.banner-item img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.banner-caption {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  padding: var(--space-4) var(--space-5);
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.65));
  color: #fff;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.banner-title {
  font-size: var(--text-lg);
  font-weight: 700;
}

.banner-desc {
  font-size: var(--text-sm);
  opacity: 0.9;
}

/* ---- v3.6.0：为你推荐 ---- */
.recommend-section {
  margin-bottom: var(--space-6);
}

.recommend-head {
  margin-bottom: var(--space-3);
}

.recommend-title {
  font-size: var(--text-xl);
  font-weight: 700;
  margin: 0;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.recommend-title .el-icon {
  color: #F9A825;
}

.recommend-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: var(--space-4);
}

.recommend-card {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  overflow: hidden;
  cursor: pointer;
  transition: all var(--transition-slow);
}

.recommend-card:hover {
  transform: translateY(-3px);
  box-shadow: var(--shadow-md);
}

.recommend-card img {
  width: 100%;
  aspect-ratio: 4 / 3;
  object-fit: cover;
  display: block;
}

.recommend-card .img-placeholder {
  aspect-ratio: 4 / 3;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-1);
  color: var(--text-muted);
  font-size: var(--text-xs);
  background: var(--neutral-100);
  padding: var(--space-2);
}

/* 无图卡片：标题与分类直接展示在图片区域内 */
.recommend-ph-title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}
.recommend-ph-meta {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

/* 推荐行末尾：大厅引导入口 */
.recommend-more {
  border: 1px dashed var(--border-light);
  border-radius: var(--radius-lg);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  padding: var(--space-3);
  min-height: 100%;
}
.recommend-more-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--el-color-primary);
  text-decoration: none;
}
.recommend-more-link:hover { text-decoration: underline; }

.recommend-body {
  padding: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.recommend-item-title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.recommend-meta {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.smart-jump { white-space: nowrap; }

/* ---- 数据看板（统计+饼图合一） ---- */
.dashboard {
  display: flex;
  gap: var(--space-5);
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  box-shadow: var(--shadow-xs);
  margin-bottom: var(--space-5);
}

.dashboard-left { flex: 1; min-width: 0; }

.stat-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-3);
  height: 100%;
}

.stat-item {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  padding: var(--space-3);
  background: var(--neutral-50);
  border-radius: var(--radius-md);
}

.stat-item .stat-num {
  font-size: var(--text-3xl);
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1;
}

.stat-item .stat-label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  margin-top: 2px;
}

.dashboard-right {
  flex-shrink: 0;
  width: 170px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.pie-mini { width: 150px; height: 150px; }

/* ---- 统计 + 校园公告：等宽等高两块 ---- */
.home-mid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-5);
  margin-bottom: var(--space-5);
  align-items: stretch;
}
.home-mid .dashboard { margin-bottom: 0; }

.announce-panel {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  box-shadow: var(--shadow-xs);
  display: flex;
  flex-direction: column;
}
.announce-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-3);
}
.announce-panel-title {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}
.announce-more {
  font-size: var(--text-sm);
  color: var(--el-color-primary);
  text-decoration: none;
}
.announce-more:hover { text-decoration: underline; }

.announce-panel-list { flex: 1; display: flex; flex-direction: column; }
.announce-panel-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) 0;
  border-bottom: 1px solid var(--border-light);
  cursor: pointer;
  transition: background var(--transition-fast);
}
.announce-panel-item:last-child { border-bottom: none; }
.announce-panel-item:hover { background: var(--neutral-50); }
.announce-panel-title-text {
  flex: 1;
  min-width: 0;
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.announce-panel-time { font-size: var(--text-xs); color: var(--text-muted); white-space: nowrap; }

@media (max-width: 640px) {
  .home-mid { grid-template-columns: 1fr; }
  .dashboard { flex-direction: column; }
  .dashboard-right { width: 100%; }
  .pie-mini { width: 120px; height: 120px; }
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
