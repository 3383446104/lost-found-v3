<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">公告管理</h1>
        <p class="page-desc">草稿/发布分离，置顶与可见范围控制</p>
      </div>
    </div>

    <div style="margin-bottom:12px">
      <el-button type="primary" size="small" @click="openAnnDialog()">
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
            <el-button size="small" @click="openAnnDialog(row)">编辑</el-button>
            <el-button v-if="row.status!=='published'" size="small" type="success" plain @click="handleTogglePublish(row, 'publish')">发布</el-button>
            <el-button v-else size="small" type="warning" plain @click="handleTogglePublish(row, 'unpublish')">下架</el-button>
            <el-button size="small" type="danger" plain @click="handleDeleteAnn(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 公告编辑对话框（富文本图文排版） -->
    <el-dialog v-model="annDialogVisible" :title="editingAnn?.id ? '编辑公告' : '新建公告'" width="720px" :close-on-click-modal="false">
      <el-form label-position="top">
        <el-form-item label="标题" required>
          <el-input v-model="annForm.title" placeholder="公告标题" maxlength="100" />
        </el-form-item>
        <el-form-item label="内容" required>
          <div class="editor-wrap">
            <Toolbar
              class="editor-toolbar"
              :editor="editorRef"
              :defaultConfig="toolbarConfig"
              mode="default"
            />
            <Editor
              v-model="annForm.content"
              class="editor-body"
              :defaultConfig="editorConfig"
              mode="default"
              @onCreated="handleEditorCreated"
            />
          </div>
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="annForm.is_pinned">置顶公告</el-checkbox>
        </el-form-item>
        <el-form-item label="可见范围">
          <el-radio-group v-model="annForm.target_role">
            <el-radio value="all">全体用户</el-radio>
            <el-radio value="user">仅普通用户</el-radio>
            <el-radio value="admin">仅管理员</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="annDialogVisible=false">取消</el-button>
        <el-button @click="handleSaveAnn('draft')" :loading="annSaving">保存草稿</el-button>
        <el-button type="primary" @click="handleSaveAnn('published')" :loading="annSaving">发布</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, shallowRef, onMounted, onBeforeUnmount } from 'vue'
import { getAnnouncements, createAnnouncement, updateAnnouncement, deleteAnnouncement, publishAnnouncement, unpublishAnnouncement, uploadAnnouncementImage } from '@/api/announcements'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import '@wangeditor/editor/dist/css/style.css'
import { Editor, Toolbar } from '@wangeditor/editor-for-vue'

// 富文本编辑器：图文排版（标题/加粗/列表/引用/图片上传等）
const editorRef = shallowRef()
const toolbarConfig = {
  excludeKeys: ['group-video', 'fullScreen', 'insertTable', 'codeBlock'],
}
const editorConfig = {
  placeholder: '请输入公告内容（支持图文排版）…',
  MENU_CONF: {
    uploadImage: {
      async customUpload(file, insertFn) {
        try {
          const res = await uploadAnnouncementImage(file)
          const url = `/api/items/uploads/${res.path}`
          insertFn(url, res.path, url)
        } catch {
          ElMessage.error('图片上传失败')
        }
      },
    },
  },
}
const handleEditorCreated = (editor) => {
  editorRef.value = editor
}
onBeforeUnmount(() => {
  editorRef.value?.destroy()
})

const announcements = ref([])
const annLoading = ref(false)
const annDialogVisible = ref(false)
const annSaving = ref(false)
const editingAnn = ref(null)
const annForm = ref({ title: '', content: '', is_pinned: false, target_role: 'all' })

// 表格预览：富文本剥离标签
const plainText = (html) => (html || '').replace(/<[^>]+>/g, '')

const loadAnnouncements = async () => {
  annLoading.value = true
  try { const r = await getAnnouncements(true); announcements.value = r.announcements || [] } catch { } finally { annLoading.value = false }
}

const openAnnDialog = (row) => {
  editingAnn.value = row || null
  annForm.value = row
    ? { title: row.title, content: row.content, is_pinned: !!row.is_pinned, target_role: row.target_role || 'all', status: row.status || 'draft' }
    : { title: '', content: '', is_pinned: false, target_role: 'all', status: 'draft' }
  annDialogVisible.value = true
}

const handleSaveAnn = async (status) => {
  if (!annForm.value.title.trim() || !annForm.value.content.trim()) { ElMessage.warning('标题和内容为必填'); return }
  annSaving.value = true
  try {
    const data = {
      title: annForm.value.title.trim(),
      content: annForm.value.content.trim(),
      is_pinned: annForm.value.is_pinned ? 1 : 0,
      target_role: annForm.value.target_role,
      status
    }
    if (editingAnn.value?.id) {
      await updateAnnouncement(editingAnn.value.id, data)
    } else {
      await createAnnouncement(data)
    }
    ElMessage.success(status === 'published' ? '已发布' : '已保存为草稿')
    annDialogVisible.value = false
    loadAnnouncements()
  } catch { } finally { annSaving.value = false }
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

/* ---- 富文本编辑器 ---- */
.editor-wrap {
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  overflow: hidden;
  width: 100%;
}
.editor-toolbar {
  border-bottom: 1px solid var(--border-light);
}
.editor-body {
  height: 280px;
  overflow-y: auto;
}
</style>
