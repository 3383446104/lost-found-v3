<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">公告管理</h1>
        <p class="page-desc">草稿/发布分离，置顶与可见范围控制；编辑在独立页面进行</p>
      </div>
    </div>

    <div style="margin-bottom:12px">
      <el-button type="primary" size="small" @click="$router.push('/admin/announcements/new')">
        <el-icon><Plus /></el-icon>新建公告
      </el-button>
    </div>
    <div v-loading="annLoading">
      <el-table :data="announcements" stripe style="width:100%">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="title" label="标题" min-width="180">
          <template #default="{ row }">
            <span>{{ row.title }}</span>
            <el-tag v-if="row.is_pinned" type="warning" size="small" style="margin-left:6px">置顶</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="target_role" label="范围" width="90">
          <template #default="{ row }">{{ row.target_role==='all'?'全体':row.target_role==='user'?'用户':'管理' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status==='published' ? 'success' : 'info'" size="small">
              {{ row.status === 'published' ? '已发布' : '草稿' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="content" label="内容" min-width="200">
          <template #default="{ row }">{{ plainText(row.content).substring(0, 60) }}{{ plainText(row.content).length > 60 ? '...' : '' }}</template>
        </el-table-column>
        <el-table-column prop="created_at" label="发布时间" width="160" />
        <el-table-column label="操作" width="220" align="center">
          <template #default="{ row }">
            <el-button size="small" @click="$router.push({ path: '/admin/announcements/edit', query: { id: row.id } })">编辑</el-button>
            <el-button v-if="row.status!=='published'" size="small" type="success" plain @click="handleTogglePublish(row, 'publish')">发布</el-button>
            <el-button v-else size="small" type="warning" plain @click="handleTogglePublish(row, 'unpublish')">下架</el-button>
            <el-button size="small" type="danger" plain @click="handleDeleteAnn(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getAnnouncements, deleteAnnouncement, publishAnnouncement, unpublishAnnouncement } from '@/api/announcements'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'

const announcements = ref([])
const annLoading = ref(false)

// 表格预览：富文本剥离标签
const plainText = (html) => (html || '').replace(/<[^>]+>/g, '')

const loadAnnouncements = async () => {
  annLoading.value = true
  try { const r = await getAnnouncements(true); announcements.value = r.announcements || [] } catch { } finally { annLoading.value = false }
}

// v3.6.0：发布/下架流转
const handleTogglePublish = async (row, action) => {
  try {
    if (action === 'publish') {
      await publishAnnouncement(row.id)
      ElMessage.success('已发布')
    } else {
      await unpublishAnnouncement(row.id)
      ElMessage.success('已下架为草稿')
    }
    loadAnnouncements()
  } catch { }
}

const handleDeleteAnn = async (id) => {
  try {
    await ElMessageBox.confirm('确认删除该公告？', '删除公告', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' })
    await deleteAnnouncement(id)
    ElMessage.success('已删除')
    loadAnnouncements()
  } catch { }
}

onMounted(loadAnnouncements)
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
  flex-wrap: wrap;
  margin-bottom: var(--space-5);
}

.page-header > div:first-child {
  flex: 1;
  min-width: 0;
}

.page-header .page-title {
  margin-bottom: var(--space-1);
}
</style>
