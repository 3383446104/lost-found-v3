<template>
  <div>
    <div class="toolbar">
      <el-button type="primary" size="small" @click="openDialog()">
        <el-icon><Plus /></el-icon>新增分类
      </el-button>
      <span class="hint">分类用于物品发布；被物品使用的分类无法删除，改名不影响历史物品</span>
    </div>

    <div v-loading="loading">
      <el-empty v-if="!loading && !categories.length" description="暂无分类" />
      <el-table v-else :data="categories" stripe style="width:100%">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="分类名" min-width="140" />
        <el-table-column prop="sort_no" label="排序" width="80" align="center" />
        <el-table-column prop="item_count" label="物品数" width="90" align="center" />
        <el-table-column label="操作" width="160" align="center">
          <template #default="{ row }">
            <el-button size="small" @click="openDialog(row)">编辑</el-button>
            <el-button size="small" type="danger" plain @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="dialogVisible" :title="editing?.id ? '编辑分类' : '新增分类'" width="380px" :close-on-click-modal="false">
      <el-form label-position="top">
        <el-form-item label="分类名" required>
          <el-input v-model="form.name" maxlength="20" placeholder="如：运动器材" />
        </el-form-item>
        <el-form-item label="排序值（越小越靠前）">
          <el-input-number v-model="form.sort_no" :min="0" />
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
import { adminCategories, createCategory, updateCategory, deleteCategory } from '@/api/categoriesAdmin'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'

const categories = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const saving = ref(false)
const editing = ref(null)
const form = ref({ name: '', sort_no: 0 })

const load = async () => {
  loading.value = true
  try {
    const res = await adminCategories()
    categories.value = res.categories || []
  } catch (e) {
    console.error('加载分类失败:', e)
  } finally {
    loading.value = false
  }
}

const openDialog = (row) => {
  editing.value = row || null
  form.value = row ? { name: row.name, sort_no: row.sort_no } : { name: '', sort_no: 0 }
  dialogVisible.value = true
}

const save = async () => {
  if (!form.value.name.trim()) { ElMessage.warning('请填写分类名'); return }
  saving.value = true
  try {
    if (editing.value?.id) {
      await updateCategory(editing.value.id, form.value)
      ElMessage.success('已更新')
    } else {
      await createCategory(form.value)
      ElMessage.success('已创建')
    }
    dialogVisible.value = false
    load()
  } catch (e) {
    console.error('保存分类失败:', e)
  } finally {
    saving.value = false
  }
}

const remove = async (row) => {
  try {
    await ElMessageBox.confirm(`确认删除分类「${row.name}」？`, '删除分类', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning'
    })
    await deleteCategory(row.id)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    // 用户取消或接口错误（拦截器已提示，如「已被物品使用」）
  }
}

onMounted(load)
</script>

<style scoped>
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: var(--space-3); flex-wrap: wrap; }
.hint { font-size: var(--text-xs); color: var(--text-tertiary); }
</style>
