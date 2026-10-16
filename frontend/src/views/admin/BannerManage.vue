<template>
  <div>
    <div class="toolbar">
      <el-button type="primary" size="small" @click="openDialog()">
        <el-icon><Plus /></el-icon>新增轮播图
      </el-button>
      <span class="hint">首页轮播展示，sort 值越小越靠前</span>
    </div>

    <div v-loading="loading">
      <el-empty v-if="!loading && !banners.length" description="暂无轮播图" />
      <el-table v-else :data="banners" stripe style="width:100%">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column label="图片" width="140">
          <template #default="{ row }">
            <img :src="getImageUrl(row.image_path)" class="banner-thumb" loading="lazy" />
          </template>
        </el-table-column>
        <el-table-column prop="title" label="标题" min-width="140" />
        <el-table-column prop="description" label="描述" min-width="160">
          <template #default="{ row }">{{ row.description || '—' }}</template>
        </el-table-column>
        <el-table-column prop="sort_no" label="排序" width="70" align="center" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 1 ? 'success' : 'info'" size="small">{{ row.status === 1 ? '启用' : '停用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" align="center">
          <template #default="{ row }">
            <el-button size="small" @click="openDialog(row)">编辑</el-button>
            <el-button size="small" type="danger" plain @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="editing?.id ? '编辑轮播图' : '新增轮播图'" width="480px" :close-on-click-modal="false">
      <el-form label-position="top">
        <el-form-item label="标题" required>
          <el-input v-model="form.title" maxlength="100" placeholder="如：新学期失物招领周" />
        </el-form-item>
        <el-form-item label="图片" required>
          <div class="img-upload-row">
            <img v-if="form.image_path" :src="getImageUrl(form.image_path)" class="banner-thumb" />
            <el-upload
              :auto-upload="false"
              :show-file-list="false"
              accept="image/*"
              :on-change="onFileChange"
            >
              <el-button size="small">{{ form.image_path ? '更换图片' : '选择图片' }}</el-button>
            </el-upload>
          </div>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" maxlength="500" show-word-limit />
        </el-form-item>
        <el-form-item label="跳转链接（可选）">
          <el-input v-model="form.link_url" maxlength="255" placeholder="如 /announcements 或 https://..." />
        </el-form-item>
        <el-form-item label="排序值（越小越靠前）">
          <el-input-number v-model="form.sort_no" :min="0" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="form.status" :active-value="1" :inactive-value="0" active-text="启用" inactive-text="停用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="save" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { adminBanners, createBanner, updateBanner, deleteBanner, uploadBanner } from '@/api/banners'
import { getImageUrl } from '@/utils/helpers'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'

const banners = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const saving = ref(false)
const editing = ref(null)
const form = ref({ title: '', image_path: '', description: '', link_url: '', sort_no: 0, status: 1 })
let pendingFile = null

const load = async () => {
  loading.value = true
  try {
    const res = await adminBanners()
    banners.value = res.banners || []
  } catch (e) {
    console.error('加载轮播图失败:', e)
  } finally {
    loading.value = false
  }
}

const openDialog = (row) => {
  editing.value = row || null
  pendingFile = null
  form.value = row
    ? { title: row.title, image_path: row.image_path, description: row.description || '', link_url: row.link_url || '', sort_no: row.sort_no, status: row.status }
    : { title: '', image_path: '', description: '', link_url: '', sort_no: 0, status: 1 }
  dialogVisible.value = true
}

const onFileChange = (file) => {
  pendingFile = file.raw
}

const save = async () => {
  if (!form.value.title.trim()) { ElMessage.warning('请填写标题'); return }
  if (!form.value.image_path && !pendingFile) { ElMessage.warning('请选择图片'); return }
  saving.value = true
  try {
    let imagePath = form.value.image_path
    if (pendingFile) {
      const up = await uploadBanner(pendingFile)
      imagePath = up.path
    }
    const data = { ...form.value, image_path: imagePath }
    if (editing.value?.id) {
      await updateBanner(editing.value.id, data)
      ElMessage.success('已更新')
    } else {
      await createBanner(data)
      ElMessage.success('已创建')
    }
    dialogVisible.value = false
    load()
  } catch (e) {
    console.error('保存轮播图失败:', e)
  } finally {
    saving.value = false
  }
}

const remove = async (row) => {
  try {
    await ElMessageBox.confirm('确认删除该轮播图？', '删除', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' })
    await deleteBanner(row.id)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    // 用户取消
  }
}

onMounted(load)
</script>

<style scoped>
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: var(--space-3); }
.hint { font-size: var(--text-xs); color: var(--text-tertiary); }
.banner-thumb { width: 100px; height: 56px; object-fit: cover; border-radius: var(--radius-sm); border: 1px solid var(--border-light); }
.img-upload-row { display: flex; gap: var(--space-3); align-items: center; }
</style>
