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

    <!-- v3.6.0：轮播图（管理员运营位） -->
    <div v-if="banners.length" class="banner-carousel">
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

    <!-- 数据看板（统计卡片 + 饼图合一） -->
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

    <!-- v3.7.0：快捷服务 4 卡（轮播图与推荐区之间） -->
    <div class="quick-services">
      <div class="quick-card" @click="$router.push({ path: '/publish', query: { type: 'lost' } })">
        <el-icon :size="22"><Search /></el-icon>
        <span class="quick-label">发布失物</span>
      </div>
      <div class="quick-card" @click="$router.push({ path: '/publish', query: { type: 'found' } })">
        <el-icon :size="22"><Box /></el-icon>
        <span class="quick-label">发布招领</span>
      </div>
      <div class="quick-card" @click="$router.push('/match')">
        <el-icon :size="22"><MagicStick /></el-icon>
        <span class="quick-label">图片匹配</span>
      </div>
      <div class="quick-card" @click="$router.push('/profile')">
        <el-icon :size="22"><User /></el-icon>
        <span class="quick-label">我的发布</span>
      </div>
    </div>

    <!-- 公告入口卡片 -->
    <div class="announce-card" v-if="announcements.length" @click="annDrawerVisible = true">
      <div class="announce-card-icon">
        <el-icon :size="20"><Bell /></el-icon>
      </div>
      <div class="announce-card-body">
        <span class="announce-card-title" v-if="pinnedAnn">{{ pinnedAnn.title }}</span>
        <span class="announce-card-title" v-else>系统公告</span>
        <span class="announce-card-hint" v-if="announcements.length > 1">共 {{ announcements.length }} 条，点击查看全部</span>
      </div>
      <el-icon class="entry-arrow"><ArrowRight /></el-icon>
    </div>

    <!-- 公告抽屉 -->
    <el-drawer v-model="annDrawerVisible" title="系统公告" size="420px" direction="rtl">
      <div class="ann-drawer-list">
        <div v-for="a in announcements" :key="a.id" class="ann-drawer-item" :class="{ pinned: a.is_pinned }">
          <div class="ann-drawer-head" @click="openAnnouncement(a)">
            <el-tag v-if="a.is_pinned" type="warning" size="small" effect="dark">置顶</el-tag>
            <el-tag size="small" :type="ANN_TYPE_MAP[a.type]?.tag || 'info'" effect="plain">
              {{ ANN_TYPE_MAP[a.type]?.label || '公告' }}
            </el-tag>
            <span class="ann-drawer-title">{{ a.title }}</span>
            <span class="ann-drawer-time">{{ a.created_at }}</span>
            <span class="ann-view-count" v-if="a.view_count">👁 {{ a.view_count }}</span>
            <el-icon class="ann-drawer-arrow" :class="{ open: a._open }"><ArrowDown /></el-icon>
          </div>
          <div class="ann-drawer-content" v-show="a._open">
            <p>{{ a.content }}</p>
          </div>
        </div>
      </div>
    </el-drawer>

    <!-- v3.7.0：双推荐区（失物 / 招领分列，复用 recommend?type=） -->
    <div v-if="recommendsLost.length || recommendsFound.length" class="recommend-duo">
      <div v-if="recommendsLost.length" class="recommend-section">
        <div class="recommend-head">
          <h2 class="recommend-title">
            <el-icon><StarFilled /></el-icon>为你推荐的失物
          </h2>
        </div>
        <div class="recommend-grid">
          <div
            v-for="r in recommendsLost"
            :key="r.id"
            class="recommend-card"
            @click="$router.push(`/items/${r.id}`)"
          >
            <img v-if="r.image_path" :src="getImageUrl(r.image_path)" :alt="r.title" loading="lazy" />
            <div v-else class="img-placeholder"><el-icon :size="28"><PictureFilled /></el-icon></div>
            <div class="recommend-body">
              <span class="recommend-item-title">{{ r.title }}</span>
              <span class="recommend-meta">{{ ITEM_TYPE_MAP[r.type]?.label }}{{ r.category ? ' · ' + r.category : '' }}</span>
            </div>
          </div>
        </div>
      </div>

      <div v-if="recommendsFound.length" class="recommend-section">
        <div class="recommend-head">
          <h2 class="recommend-title">
            <el-icon><StarFilled /></el-icon>为你推荐的招领
          </h2>
        </div>
        <div class="recommend-grid">
          <div
            v-for="r in recommendsFound"
            :key="r.id"
            class="recommend-card"
            @click="$router.push(`/items/${r.id}`)"
          >
            <img v-if="r.image_path" :src="getImageUrl(r.image_path)" :alt="r.title" loading="lazy" />
            <div v-else class="img-placeholder"><el-icon :size="28"><PictureFilled /></el-icon></div>
            <div class="recommend-body">
              <span class="recommend-item-title">{{ r.title }}</span>
              <span class="recommend-meta">{{ ITEM_TYPE_MAP[r.type]?.label }}{{ r.category ? ' · ' + r.category : '' }}</span>
            </div>
          </div>
        </div>
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
            <span class="card-views" v-if="item.view_count">👁 {{ item.view_count }}</span>
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
import { ref, onMounted, onUnmounted, computed, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { getItems, getCategories, getRecommend } from '@/api/items'
import { publicBanners } from '@/api/banners'
import { getImageUrl, ITEM_TYPE_MAP, REVIEW_STATUS_MAP, truncate } from '@/utils/helpers'
import { Search, PictureFilled, Folder, LocationFilled, Plus, MagicStick, StarFilled, Box, User } from '@element-plus/icons-vue'
import SkeletonCard from '@/components/SkeletonCard.vue'
import request from '@/utils/request'
import { getAnnouncements, getAnnouncement } from '@/api/announcements'
import { Bell, ArrowRight, ArrowDown } from '@element-plus/icons-vue'
import * as echarts from 'echarts'

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
const annDrawerVisible = ref(false)
// v3.6.0：轮播图 + 为你推荐
const banners = ref([])
// v3.7.0：双推荐区（失物 / 招领分列）
const recommendsLost = ref([])
const recommendsFound = ref([])

// v3.7.0：公告类型打标
const ANN_TYPE_MAP = {
  system: { label: '系统公告', tag: 'info' },
  lost: { label: '失物提醒', tag: 'danger' },
  found: { label: '招领提醒', tag: 'success' },
}

const pinnedAnn = computed(() => announcements.value.find(a => a.is_pinned))
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
  try { const res = await getAnnouncements(); announcements.value = res.announcements || [] } catch { }
}

// v3.7.0：展开公告调详情接口（浏览数自增），并把最新数据并回列表项
const openAnnouncement = async (a) => {
  const willOpen = !a._open
  a._open = willOpen
  if (!willOpen) return
  try {
    const res = await getAnnouncement(a.id)
    if (res.announcement) {
      Object.assign(a, res.announcement, { _open: true })
    }
  } catch { /* 打开失败保持原内容 */ }
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
  // v3.7.0：双推荐区——失物 / 招领分别拉取
  try {
    const [lostRes, foundRes] = await Promise.all([
      getRecommend({ limit: 8, type: 'lost' }),
      getRecommend({ limit: 8, type: 'found' }),
    ])
    recommendsLost.value = lostRes.items || []
    recommendsFound.value = foundRes.items || []
  } catch { }
}

onMounted(() => {
  getCategories().then(res => { categories.value = res.categories || [] }).catch(() => {})
  loadItems()
  loadStats()
  loadAnnouncements()
  loadBanners()
  loadRecommends()
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
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  background: var(--neutral-100);
}

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

/* ---- 公告入口卡片 ---- */
.announce-card {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-4);
  background: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-6);
  border-radius: var(--radius-lg);
  cursor: pointer;
  margin-bottom: var(--space-5);
  transition: all var(--transition-fast);
}
.announce-card:hover { border-color: var(--el-color-primary); box-shadow: var(--shadow-sm); }
.announce-card-icon {
  width: 40px; height: 40px; border-radius: 50%;
  background: var(--el-color-primary);
  color: white;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.announce-card-body { flex: 1; min-width: 0; }
.announce-card-title { font-weight: 600; color: var(--el-color-primary); font-size: var(--text-base); }
.announce-card-hint { display: block; font-size: var(--text-xs); color: var(--text-tertiary); margin-top: 2px; }
.entry-arrow { color: var(--el-color-primary); flex-shrink: 0; }

/* ---- 公告抽屉 ---- */
.ann-drawer-list { display: flex; flex-direction: column; gap: var(--space-2); padding: 0 var(--space-4); }
.ann-drawer-item { border: 1px solid var(--border-light); border-radius: var(--radius-md); overflow: hidden; }
.ann-drawer-item.pinned { border-color: #FFE082; background: #FFFDF5; }
.ann-drawer-head {
  display: flex; align-items: center; gap: var(--space-2);
  padding: var(--space-3) var(--space-4); cursor: pointer;
  transition: background var(--transition-fast);
}
.ann-drawer-head:hover { background: var(--neutral-50); }
.ann-drawer-title { font-weight: 500; color: var(--text-primary); flex: 1; }
.ann-drawer-time { font-size: var(--text-xs); color: var(--text-muted); white-space: nowrap; }
.ann-drawer-arrow { color: var(--text-muted); transition: transform var(--transition-fast); flex-shrink: 0; }
.ann-drawer-arrow.open { transform: rotate(180deg); }
.ann-drawer-content {
  padding: 0 var(--space-4) var(--space-4);
  font-size: var(--text-base); line-height: 1.8; color: var(--text-secondary);
  border-top: 1px solid var(--border-light);
  margin: 0 var(--space-4);
}
.ann-drawer-content p { margin: var(--space-3) 0 0; }

@media (max-width: 640px) {
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

/* ---- v3.7.0：快捷服务 4 卡 ---- */
.quick-services {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-4);
  margin-bottom: var(--space-5);
}
.quick-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-4);
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  cursor: pointer;
  color: var(--el-color-primary);
  transition: all var(--transition-base);
}
.quick-card:hover { border-color: var(--el-color-primary); box-shadow: var(--shadow-xs); }
.quick-label { font-size: var(--text-sm); font-weight: 600; color: var(--text-secondary); }

/* ---- v3.7.0：双推荐区 / 浏览数 / 公告类型 ---- */
.recommend-duo { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-5); }
.ann-view-count { font-size: var(--text-xs); color: var(--text-tertiary); margin-left: auto; }
.card-views { font-size: var(--text-xs); color: var(--text-tertiary); display: inline-flex; align-items: center; gap: 2px; }
@media (max-width: 640px) {
  .quick-services { grid-template-columns: repeat(2, 1fr); }
  .recommend-duo { grid-template-columns: 1fr; }
}
</style>
