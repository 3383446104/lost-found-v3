<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">{{ isEdit ? '编辑公告' : '新建公告' }}</h1>
        <p class="page-desc">图文排版内容将在发布时推送给所有用户（站内通知 + 邮件）</p>
      </div>
    </div>

    <div class="card edit-card" v-loading="loading">
      <el-form label-position="top">
        <el-form-item label="标题" required>
          <el-input v-model="form.title" placeholder="公告标题" maxlength="100" size="large" />
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
              v-model="form.content"
              class="editor-body"
              :defaultConfig="editorConfig"
              mode="default"
              @onCreated="handleEditorCreated"
            />
          </div>
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="form.is_pinned">置顶公告</el-checkbox>
        </el-form-item>
        <el-form-item label="可见范围">
          <el-radio-group v-model="form.target_role">
            <el-radio value="all">全体用户</el-radio>
            <el-radio value="user">仅普通用户</el-radio>
            <el-radio value="admin">仅管理员</el-radio>
          </el-radio-group>
        </el-form-item>
        <div class="form-actions">
          <el-button @click="$router.push('/admin/announcements')">取消</el-button>
          <el-button :loading="saving" @click="save('draft')">保存草稿</el-button>
          <el-button type="primary" :loading="saving" @click="save('published')">发布</el-button>
        </div>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, shallowRef, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  getAnnouncement, createAnnouncement, updateAnnouncement, uploadAnnouncementImage,
} from '@/api/announcements'
import { ElMessage } from 'element-plus'
import '@wangeditor/editor/dist/css/style.css'
import { Editor, Toolbar } from '@wangeditor/editor-for-vue'

const route = useRoute()
const router = useRouter()
const isEdit = computed(() => !!route.query.id)
const loading = ref(false)
const saving = ref(false)
const form = reactive({ title: '', content: '', is_pinned: false, target_role: 'all' })

// 富文本编辑器：图文排版
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

const loadForEdit = async () => {
  loading.value = true
  try {
    const res = await getAnnouncement(route.query.id)
    if (res.announcement) {
      form.title = res.announcement.title || ''
      form.content = res.announcement.content || ''
      form.is_pinned = !!res.announcement.is_pinned
      form.target_role = res.announcement.target_role || 'all'
    }
  } catch {
    ElMessage.error('无法加载公告信息')
    router.push('/admin/announcements')
  } finally {
    loading.value = false
  }
}

const save = async (status) => {
  if (!form.title.trim()) { ElMessage.warning('标题不能为空'); return }
  if (!form.content.replace(/<[^>]+>/g, '').trim()) { ElMessage.warning('内容不能为空'); return }
  saving.value = true
  try {
    const data = {
      title: form.title.trim(),
      content: form.content,
      is_pinned: form.is_pinned ? 1 : 0,
      target_role: form.target_role,
      status,
    }
    if (isEdit.value) {
      await updateAnnouncement(route.query.id, data)
    } else {
      await createAnnouncement(data)
    }
    ElMessage.success(status === 'published' ? '已发布，已推送所有用户' : '已保存为草稿')
    router.push('/admin/announcements')
  } catch {} finally { saving.value = false }
}

onMounted(() => {
  if (isEdit.value) loadForEdit()
})
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
.page-header > div:first-child { flex: 1; min-width: 0; }
.page-header .page-title { margin-bottom: var(--space-1); }

.card {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-xs);
}
.edit-card { padding: var(--space-6); max-width: 960px; }

.editor-wrap {
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  overflow: hidden;
  width: 100%;
}
.editor-toolbar { border-bottom: 1px solid var(--border-light); }
.editor-body { height: 480px; overflow-y: auto; }

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-3);
  margin-top: var(--space-2);
}
</style>
