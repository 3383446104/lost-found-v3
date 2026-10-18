<template>
  <div class="page-container viz-root">
    <div class="page-header">
      <h1 class="page-title">数据统计</h1>
      <p class="page-desc">平台运营指标总览（找回率 / 发布趋势 / 分类分布）</p>
    </div>

    <!-- 指标卡 -->
    <div class="stat-tiles">
      <div class="tile">
        <span class="tile-num">{{ overview.item_total ?? '—' }}</span>
        <span class="tile-label">物品总数</span>
      </div>
      <div class="tile tile--warn">
        <span class="tile-num">{{ overview.pending_review ?? '—' }}</span>
        <span class="tile-label">待审核</span>
      </div>
      <div class="tile">
        <span class="tile-num">{{ overview.claiming_count ?? '—' }}</span>
        <span class="tile-label">认领中</span>
      </div>
      <div class="tile tile--good">
        <span class="tile-num">{{ overview.claimed_total ?? '—' }}</span>
        <span class="tile-label">已完成</span>
      </div>
      <div class="tile">
        <span class="tile-num">{{ overview.user_total ?? '—' }}</span>
        <span class="tile-label">活跃用户</span>
      </div>
    </div>

    <!-- 图表区：找回率(1/3) + 发布趋势(2/3) 并排；分类占比全宽 -->
    <div class="charts-grid">
      <!-- 找回率 -->
      <div class="chart-card">
        <h2 class="chart-title">找回率</h2>
        <div class="recovery-ring" ref="recoveryRef"></div>
        <p class="recovery-caption">已完成 {{ recovery.claimed_total }} / 已处理物品 {{ recovery.processed_total }}</p>
        <div class="recovery-stats">
          <div class="r-stat">
            <span class="r-stat-num">{{ recovery.by_type?.lost ?? 0 }}</span>
            <span class="r-stat-label">失物找回</span>
          </div>
          <div class="r-stat">
            <span class="r-stat-num">{{ recovery.by_type?.found ?? 0 }}</span>
            <span class="r-stat-label">招领找回</span>
          </div>
          <div class="r-stat">
            <span class="r-stat-num">{{ recovery.completed_claims ?? 0 }}</span>
            <span class="r-stat-label">完成认领单</span>
          </div>
        </div>
      </div>

      <!-- 发布趋势 -->
      <div class="chart-card">
        <h2 class="chart-title">近 {{ trendDays }} 天发布趋势</h2>
        <div class="chart-box" ref="trendRef"></div>
        <el-table :data="trend" size="small" class="trend-table" max-height="160">
          <el-table-column prop="date" label="日期" width="100" />
          <el-table-column prop="lost" label="失物" width="100" />
          <el-table-column prop="found" label="招领" width="100" />
        </el-table>
      </div>

      <!-- 分类占比：饼图与表格左右并排 -->
      <div class="chart-card chart-card--wide pie-card">
        <h2 class="chart-title">分类占比（展示中物品）</h2>
        <div class="pie-card-body">
          <div class="chart-box chart-box--pie" ref="pieRef"></div>
          <el-table :data="categories" size="small" class="pie-table" max-height="300">
            <el-table-column prop="name" label="分类" />
            <el-table-column prop="count" label="数量" width="80" align="right" />
            <el-table-column label="占比" width="90" align="right">
              <template #default="{ row }">
                {{ percentOf(row.count) }}
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { adminOverview, adminRecovery, adminPublishTrend, adminCategoryPie } from '@/api/stats'
import * as echarts from 'echarts'

// 图表调色板（dataviz 已验证：相邻对 CVD ΔE ≥ 8，浅色面 3:1 对比不足的槽位由表格视图兜底）
const CAT_COLORS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948']
const TREND_COLORS = { lost: '#2a78d6', found: '#eb6834' }
const MUTED_INK = '#898781'

const overview = ref({})
const recovery = ref({ recovery_rate: 0, claimed_total: 0, processed_total: 0, completed_claims: 0, by_type: {} })
const trend = ref([])
const trendDays = ref(30)
const categories = ref([])

const recoveryRef = ref(null)
const trendRef = ref(null)
const pieRef = ref(null)
let recoveryChart = null
let trendChart = null
let pieChart = null

const totalCategoryCount = computed(() => categories.value.reduce((s, c) => s + c.count, 0))
const percentOf = (count) => (totalCategoryCount.value ? ((count / totalCategoryCount.value) * 100).toFixed(1) + '%' : '—')

const primaryInk = () =>
  (typeof document !== 'undefined' && document.documentElement.dataset.theme === 'dark') ? '#f0efec' : '#0b0b0b'

const renderRecovery = () => {
  if (!recoveryRef.value) return
  if (!recoveryChart) recoveryChart = echarts.init(recoveryRef.value)
  const rate = recovery.value.recovery_rate || 0
  recoveryChart.setOption({
    series: [{
      type: 'gauge',
      startAngle: 210,
      endAngle: -30,
      min: 0,
      max: 1,
      radius: '100%',
      center: ['50%', '58%'],
      progress: { show: true, width: 12, roundCap: true, itemStyle: { color: '#1baf7a' } },
      axisLine: { lineStyle: { width: 12, color: [[1, '#e1e0d9']] } },
      axisTick: { show: false },
      splitLine: { show: false },
      axisLabel: { show: false },
      pointer: { show: false },
      anchor: { show: false },
      title: { show: false },
      detail: {
        valueAnimation: true,
        fontSize: 30,
        fontWeight: 700,
        color: primaryInk(),
        formatter: (v) => (v * 100).toFixed(1) + '%',
        offsetCenter: [0, '42%']
      },
      data: [{ value: rate, name: '找回率' }]
    }]
  })
}

const renderTrend = () => {
  if (!trendRef.value) return
  if (!trendChart) trendChart = echarts.init(trendRef.value)
  const days = trend.value.map((t) => t.date)
  trendChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['失物', '招领'], top: 0, textStyle: { color: primaryInk() } },
    grid: { left: 8, right: 16, top: 36, bottom: 8, containLabel: true },
    xAxis: {
      type: 'category',
      data: days,
      axisLine: { lineStyle: { color: '#c3c2b7' } },
      axisLabel: { color: MUTED_INK, fontSize: 10 },
      axisTick: { show: false }
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      axisLabel: { color: MUTED_INK, fontSize: 10 },
      splitLine: { lineStyle: { color: '#e1e0d9' } }
    },
    series: [
      {
        name: '失物',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 5,
        lineStyle: { width: 2, color: TREND_COLORS.lost },
        itemStyle: { color: TREND_COLORS.lost },
        areaStyle: { opacity: 0.06, color: TREND_COLORS.lost },
        data: trend.value.map((t) => t.lost)
      },
      {
        name: '招领',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 5,
        lineStyle: { width: 2, color: TREND_COLORS.found },
        itemStyle: { color: TREND_COLORS.found },
        areaStyle: { opacity: 0.06, color: TREND_COLORS.found },
        data: trend.value.map((t) => t.found)
      }
    ]
  })
}

const renderPie = () => {
  if (!pieRef.value) return
  if (!pieChart) pieChart = echarts.init(pieRef.value)
  pieChart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: {
      orient: 'vertical',
      right: 0,
      top: 'middle',
      itemWidth: 10,
      itemHeight: 10,
      textStyle: { color: primaryInk(), fontSize: 12 }
    },
    series: [{
      type: 'pie',
      radius: ['42%', '72%'],
      center: ['38%', '50%'],
      itemStyle: { borderColor: 'transparent', borderWidth: 2, borderRadius: 4 },
      label: { show: false },
      emphasis: { label: { show: true, color: primaryInk(), fontWeight: 700 } },
      data: categories.value.map((c) => ({ name: c.name, value: c.count }))
    }],
    color: CAT_COLORS
  })
}

const loadAll = async () => {
  try { overview.value = (await adminOverview()).data || {} } catch (e) { console.error('overview 加载失败:', e) }
  try {
    const d = (await adminRecovery()).data || {}
    recovery.value = { recovery_rate: 0, claimed_total: 0, processed_total: 0, completed_claims: 0, by_type: {}, ...d }
    renderRecovery()
  } catch (e) { console.error('recovery 加载失败:', e) }
  try {
    const d = (await adminPublishTrend(trendDays.value)).data || {}
    trend.value = d.trend || []
    renderTrend()
  } catch (e) { console.error('trend 加载失败:', e) }
  try {
    const d = (await adminCategoryPie()).data || {}
    categories.value = d.categories || []
    renderPie()
  } catch (e) { console.error('pie 加载失败:', e) }
}

const handleResize = () => {
  recoveryChart?.resize()
  trendChart?.resize()
  pieChart?.resize()
}

onMounted(() => {
  loadAll()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  recoveryChart?.dispose(); recoveryChart = null
  trendChart?.dispose(); trendChart = null
  pieChart?.dispose(); pieChart = null
})
</script>

<style scoped>
.page-header { margin-bottom: var(--space-5); }
.page-title { margin-bottom: var(--space-1); }
.page-desc { color: var(--text-tertiary); font-size: var(--text-sm); margin: 0; }

/* 指标卡 */
.stat-tiles {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: var(--space-4);
  margin-bottom: var(--space-6);
}

.tile {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.tile-num {
  font-size: var(--text-3xl);
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.tile--warn .tile-num { color: #E65100; }
.tile--good .tile-num { color: #2E7D32; }

.tile-label { font-size: var(--text-xs); color: var(--text-tertiary); }

/* 图表区：找回率(1fr) + 趋势(2fr) 并排；分类占比全宽 */
.charts-grid {
  display: grid;
  grid-template-columns: 1fr 2fr;
  gap: var(--space-5);
  align-items: stretch;
}

.chart-card {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  box-shadow: var(--shadow-xs);
  display: flex;
  flex-direction: column;
}

.chart-card--wide { grid-column: 1 / -1; }

.chart-title {
  font-size: var(--text-lg);
  font-weight: 700;
  margin: 0 0 var(--space-4);
  color: var(--text-primary);
}

.chart-box { width: 100%; height: 300px; }

/* 找回率卡 */
.recovery-ring { width: 100%; height: 210px; }
.recovery-caption {
  text-align: center;
  color: var(--text-tertiary);
  font-size: var(--text-sm);
  margin: var(--space-3) 0 0;
}
.recovery-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-2);
  margin-top: var(--space-4);
  padding-top: var(--space-4);
  border-top: 1px solid var(--border-light);
}
.r-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}
.r-stat-num {
  font-size: var(--text-xl);
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}
.r-stat-label { font-size: var(--text-xs); color: var(--text-tertiary); }

.trend-table { margin-top: var(--space-3); }

/* 分类占比：饼图 + 表格左右并排 */
.pie-card-body {
  display: flex;
  gap: var(--space-6);
  align-items: stretch;
  flex: 1;
  min-height: 300px;
}
.chart-box--pie { flex: 1; min-width: 0; height: auto; min-height: 300px; }
.pie-table { width: 46%; flex-shrink: 0; }

@media (max-width: 768px) {
  .charts-grid { grid-template-columns: 1fr; }
  .chart-card--wide { grid-column: auto; }
  .chart-box { height: 220px; }
  .pie-card-body { flex-direction: column; }
  .chart-box--pie { min-height: 240px; }
  .pie-table { width: 100%; }
}
</style>
