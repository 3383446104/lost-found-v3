<template>
  <div class="page-container">
    <h1 class="page-title">管理面板</h1>

    <el-tabs v-model="activeTab" type="border-card">
      <!-- ====== 审核管理 Tab ====== -->
      <el-tab-pane label="物品审核" name="review">
        <div class="page-header">
          <div>
            <p class="page-desc">审核用户发布的物品，通过后将自动进行智能匹配并通知相关用户</p>
          </div>
          <span v-if="items.length && !loading" class="pending-count">
            {{ total }} 条待审
          </span>
        </div>

        <!-- v3.3: 批量操作工具栏（使用表格内置全选复选框） -->
        <div v-if="items.length && !loading" class="batch-toolbar">
          <span class="batch-hint">勾选表格行进行批量操作</span>
          <el-button
            type="success"
            :disabled="selectedIds.length === 0"
            @click="handleBatchApprove"
            :loading="batchLoading"
          >
            一键批量通过 (已选 {{ selectedIds.length }} 条)
          </el-button>
        </div>

        <el-empty v-if="items.length === 0 && !loading" description="暂无待审核物品" />

        <div v-else class="review-table-wrap">
      <el-table
        :data="items"
        style="width:100%"
        stripe
        row-key="id"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="44" />
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="expand-content">
              <div class="expand-img" v-if="row.image_path">
                <img :src="getImageUrl(row.image_path)" :alt="row.title" loading="lazy" />
              </div>
              <div v-else class="expand-img img-placeholder">
                <el-icon :size="28"><PictureFilled /></el-icon>
                <span>暂无图片</span>
              </div>
              <div class="expand-info">
                <div class="expand-field">
                  <span class="field-label">描述</span>
                  <span class="field-value">{{ row.description || '无描述' }}</span>
                </div>
                <div class="expand-field">
                  <span class="field-label">位置</span>
                  <span class="field-value">{{ row.location || '未填写' }}</span>
                </div>
                <div class="expand-field">
                  <span class="field-label">分类</span>
                  <span class="field-value">{{ row.category || '未分类' }}</span>
                </div>
              </div>
              <div class="expand-actions">
                <el-button type="success" @click="approve(row.id)" size="default">
                  <el-icon><Select /></el-icon>通过
                </el-button>
                <el-button type="danger" @click="reject(row.id)" size="default" plain>
                  <el-icon><CloseBold /></el-icon>驳回
                </el-button>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="id" label="ID" width="64" align="center" />
        <el-table-column prop="title" label="标题" min-width="180">
          <template #default="{ row }">
            <router-link :to="`/items/${row.id}`" class="item-link">{{ row.title }}</router-link>
          </template>
        </el-table-column>
        <el-table-column prop="type" label="类型" width="90" align="center">
          <template #default="{ row }">
            <span
              class="status-tag"
              :style="{ background: ITEM_TYPE_MAP[row.type]?.bg, color: ITEM_TYPE_MAP[row.type]?.color }"
            >
              {{ ITEM_TYPE_MAP[row.type]?.label }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="category" label="分类" width="110" />
        <el-table-column prop="created_at" label="发布时间" width="170" />
        <el-table-column label="操作" width="170" align="center" fixed="right">
          <template #default="{ row }">
            <div class="action-btns">
              <el-button type="success" size="small" @click="approve(row.id)">通过</el-button>
              <el-button type="danger" size="small" @click="reject(row.id)" plain>驳回</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
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

    <!-- 驳回对话框 -->
    <el-dialog v-model="dialogVisible" title="驳回物品" width="440px" :close-on-click-modal="false">
      <el-form label-position="top">
        <el-form-item label="驳回理由（必填）">
          <el-input
            v-model="reason"
            type="textarea"
            :rows="4"
            placeholder="请填写驳回理由，帮助用户修改..."
            maxlength="200"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="danger" @click="confirmReject" :loading="rejecting">确认驳回</el-button>
      </template>
    </el-dialog>
      </el-tab-pane>

      <!-- ====== 用户管理 Tab ====== -->
      <el-tab-pane label="用户管理" name="users">
        <div style="margin-bottom:12px">
          <el-button type="primary" size="small" @click="openCreateUserDialog">
            <el-icon><Plus /></el-icon>新增用户
          </el-button>
        </div>
        <div v-loading="userLoading">
          <el-table :data="users" stripe style="width:100%">
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column prop="username" label="用户名" min-width="140" />
            <el-table-column prop="role" label="角色" width="110">
              <template #default="{ row }">
                <el-tag :type="row.role==='admin'?'success':row.role==='disabled'?'danger':''" size="small">
                  {{ row.role === 'admin' ? '管理员' : row.role === 'disabled' ? '已禁用' : '用户' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="phone" label="手机号" width="130" />
            <el-table-column prop="email" label="邮箱" min-width="160" />
            <el-table-column prop="created_at" label="注册时间" width="170" />
            <el-table-column label="操作" width="200" align="center">
              <template #default="{ row }">
                <el-button v-if="row.role==='user'" type="primary" size="small" @click="setUserRole(row.id,'admin')">设为管理</el-button>
                <el-button v-if="row.role==='admin'" size="small" @click="setUserRole(row.id,'user')">取消管理</el-button>
                <el-button v-if="row.role!=='disabled'" type="danger" size="small" plain @click="toggleUser(row.id)">禁用</el-button>
                <el-button v-else type="success" size="small" @click="toggleUser(row.id)">启用</el-button>
                <el-button type="danger" size="small" plain @click="handleDeleteUser(row)" :disabled="row.role==='deleted'">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-pagination
            v-if="userTotal > userPageSize"
            v-model:current-page="userPage"
            :page-size="userPageSize"
            :total="userTotal"
            layout="prev, pager, next"
            @current-change="loadUsers"
            style="margin-top:20px;justify-content:center"
          />
        </div>
      </el-tab-pane>

      <!-- ====== 公告管理 Tab ====== -->
      <el-tab-pane label="公告管理" name="announce">
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
            <el-table-column prop="content" label="内容" min-width="200">
              <template #default="{ row }">{{ row.content?.substring(0, 60) }}{{ row.content?.length > 60 ? '...' : '' }}</template>
            </el-table-column>
            <el-table-column prop="created_at" label="发布时间" width="160" />
            <el-table-column label="操作" width="140" align="center">
              <template #default="{ row }">
                <el-button size="small" @click="openAnnDialog(row)">编辑</el-button>
                <el-button size="small" type="danger" plain @click="handleDeleteAnn(row.id)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 公告编辑对话框 -->
    <el-dialog v-model="annDialogVisible" :title="editingAnn?.id ? '编辑公告' : '新建公告'" width="500px" :close-on-click-modal="false">
      <el-form label-position="top">
        <el-form-item label="标题" required>
          <el-input v-model="annForm.title" placeholder="公告标题" maxlength="100" />
        </el-form-item>
        <el-form-item label="内容" required>
          <el-input v-model="annForm.content" type="textarea" :rows="5" placeholder="公告内容" maxlength="1000" show-word-limit />
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="annForm.is_pinned">置顶公告</el-checkbox>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="annDialogVisible=false">取消</el-button>
        <el-button type="primary" @click="handleSaveAnn" :loading="annSaving">{{ editingAnn?.id ? '保存' : '发布' }}</el-button>
      </template>
    </el-dialog>

    <!-- 新增用户对话框 -->
    <el-dialog v-model="createUserVisible" title="新增用户" width="440px" :close-on-click-modal="false">
      <el-form :model="newUserForm" label-position="top">
        <el-form-item label="用户名" required>
          <el-input v-model="newUserForm.username" placeholder="2-20位" maxlength="20" />
        </el-form-item>
        <el-form-item label="密码" required>
          <el-input v-model="newUserForm.password" type="password" placeholder="6-30位" show-password />
        </el-form-item>
        <el-form-item label="手机号">
          <el-input v-model="newUserForm.phone" placeholder="选填" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="newUserForm.email" placeholder="选填" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="newUserForm.role" style="width:100%">
            <el-option label="普通用户" value="user" />
            <el-option label="管理员" value="admin" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createUserVisible=false">取消</el-button>
        <el-button type="primary" @click="handleCreateUser" :loading="creatingUser">确认创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getPendingItems, reviewItem, batchApprove, getUsers, updateUser, createUser, deleteUser } from '@/api/admin'
import { getAnnouncements, createAnnouncement, updateAnnouncement, deleteAnnouncement } from '@/api/announcements'
import { getImageUrl, ITEM_TYPE_MAP } from '@/utils/helpers'
import { ElMessage, ElMessageBox } from 'element-plus'
import { PictureFilled, Select, CloseBold, Plus, Edit } from '@element-plus/icons-vue'

const activeTab = ref('review')
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const dialogVisible = ref(false)
const reason = ref('')
const currentId = ref(null)
const rejecting = ref(false)
// v3.3 批量审核
const selectedIds = ref([])
const batchLoading = ref(false)

// 用户管理
const users = ref([])
const userTotal = ref(0)
const userPage = ref(1)
const userPageSize = ref(20)
const userLoading = ref(false)
const createUserVisible = ref(false)
const creatingUser = ref(false)
const newUserForm = ref({ username: '', password: '', phone: '', email: '', role: 'user' })

const loadItems = async () => {
  loading.value = true
  try {
    const res = await getPendingItems(page.value, pageSize.value)
    items.value = res.items || []
    total.value = res.total || 0
  } catch (e) {
    console.error('加载审核列表失败', e)
  } finally {
    loading.value = false
  }
}

const approve = async (id) => {
  try {
    await reviewItem(id, { action: 'approved' })
    ElMessage.success('审核通过，已自动匹配并通知相关用户')
    loadItems()
  } catch {
    // 错误已在拦截器处理
  }
}

const reject = (id) => {
  currentId.value = id
  reason.value = ''
  dialogVisible.value = true
}

const confirmReject = async () => {
  if (!reason.value.trim()) {
    ElMessage.warning('请填写驳回理由')
    return
  }
  rejecting.value = true
  try {
    await reviewItem(currentId.value, { action: 'rejected', reason: reason.value.trim() })
    ElMessage.success('已驳回')
    dialogVisible.value = false
    loadItems()
  } catch {
    // 错误已在拦截器处理
  } finally {
    rejecting.value = false
  }
}

// v3.3: 批量审核
const handleSelectionChange = (val) => {
  selectedIds.value = val.map(v => v.id)
}

const handleBatchApprove = async () => {
  if (selectedIds.value.length === 0) { ElMessage.warning('请至少选择一条'); return }
  try {
    await ElMessageBox.confirm(
      `即将通过 ${selectedIds.value.length} 件物品的审核，通过后将自动进行智能匹配并通知相关用户。`,
      '确认批量审核',
      { confirmButtonText: `确认通过 ${selectedIds.value.length} 件`, cancelButtonText: '取消', type: 'success' }
    )
  } catch {
    return  // 用户取消，直接返回
  }

  batchLoading.value = true
  try {
    const res = await batchApprove(selectedIds.value)
    const failedCount = res.failed_ids?.length || 0
    if (failedCount > 0) {
      ElMessage.warning(`已通过 ${res.approved_count} 件，${failedCount} 件失败（可能已被他人审核）`)
    } else {
      ElMessage.success(`已批量通过 ${res.approved_count} 件物品，匹配通知已发送`)
    }
    selectedIds.value = []
    loadItems()
  } catch (e) {
    console.error('批量审核失败:', e)
    // axios 拦截器已显示错误消息，此处仅做清理
  } finally {
    batchLoading.value = false
  }
}

const loadUsers = async () => {
  userLoading.value = true
  try {
    const res = await getUsers(userPage.value, userPageSize.value)
    users.value = res.users || []
    userTotal.value = res.total || 0
  } catch { } finally { userLoading.value = false }
}

const setUserRole = async (id, role) => {
  try {
    await updateUser(id, { action: 'set_role', role })
    ElMessage.success('角色已更新')
    loadUsers()
  } catch { }
}

const toggleUser = async (id) => {
  try {
    await updateUser(id, { action: 'toggle_status' })
    ElMessage.success('操作成功')
    loadUsers()
  } catch { }
}

const openCreateUserDialog = () => {
  newUserForm.value = { username: '', password: '', phone: '', email: '', role: 'user' }
  createUserVisible.value = true
}

const handleCreateUser = async () => {
  const f = newUserForm.value
  if (!f.username.trim() || !f.password.trim()) {
    ElMessage.warning('用户名和密码为必填')
    return
  }
  creatingUser.value = true
  try {
    await createUser({ username: f.username.trim(), password: f.password, phone: f.phone, email: f.email, role: f.role })
    ElMessage.success('用户已创建')
    createUserVisible.value = false
    loadUsers()
  } catch { } finally { creatingUser.value = false }
}

const handleDeleteUser = async (row) => {
  try {
    await ElMessageBox.confirm(`确认删除用户 "${row.username}"？其所有物品将被关闭。`, '删除用户', {
      confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'error'
    })
    await deleteUser(row.id)
    ElMessage.success('用户已删除')
    loadUsers()
  } catch { }
}

// 公告管理
const announcements = ref([])
const annLoading = ref(false)
const annDialogVisible = ref(false)
const annSaving = ref(false)
const editingAnn = ref(null)
const annForm = ref({ title: '', content: '', is_pinned: false })

const loadAnnouncements = async () => {
  annLoading.value = true
  try { const r = await getAnnouncements(); announcements.value = r.announcements || [] } catch { } finally { annLoading.value = false }
}

const openAnnDialog = (row) => {
  editingAnn.value = row || null
  annForm.value = row ? { title: row.title, content: row.content, is_pinned: !!row.is_pinned } : { title: '', content: '', is_pinned: false }
  annDialogVisible.value = true
}

const handleSaveAnn = async () => {
  if (!annForm.value.title.trim() || !annForm.value.content.trim()) { ElMessage.warning('标题和内容为必填'); return }
  annSaving.value = true
  try {
    const data = { title: annForm.value.title.trim(), content: annForm.value.content.trim(), is_pinned: annForm.value.is_pinned ? 1 : 0 }
    if (editingAnn.value?.id) { await updateAnnouncement(editingAnn.value.id, data) } else { await createAnnouncement(data) }
    ElMessage.success(editingAnn.value?.id ? '已更新' : '已发布')
    annDialogVisible.value = false
    loadAnnouncements()
  } catch { } finally { annSaving.value = false }
}

const handleDeleteAnn = async (id) => {
  try {
    await ElMessageBox.confirm('确认删除该公告？', '删除公告', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' })
    await deleteAnnouncement(id)
    ElMessage.success('已删除')
    loadAnnouncements()
  } catch { }
}

onMounted(() => { loadItems(); loadUsers(); loadAnnouncements() })
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

.pending-count {
  flex-shrink: 0;
  background: var(--el-color-warning);
  color: white;
  padding: 4px 14px;
  border-radius: var(--radius-full);
  font-size: var(--text-sm);
  font-weight: 600;
  white-space: nowrap;
  margin-top: 2px;
}

.review-table-wrap {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  overflow: hidden;
  border: 1px solid var(--border-light);
  box-shadow: var(--shadow-xs);
}

.item-link {
  color: var(--el-color-primary);
  text-decoration: none;
  font-weight: 500;
}

.item-link:hover {
  text-decoration: underline;
}

.action-btns {
  display: flex;
  gap: 6px;
  justify-content: center;
}

/* 展开行 */
.expand-content {
  display: flex;
  gap: var(--space-6);
  padding: var(--space-5) var(--space-6);
  align-items: flex-start;
}

.expand-img {
  width: 160px;
  flex-shrink: 0;
  border-radius: var(--radius-md);
  overflow: hidden;
  background: var(--neutral-100);
  aspect-ratio: 4/3;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--text-muted);
}

.expand-img img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.expand-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.expand-field {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.field-label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-weight: 500;
}

.field-value {
  font-size: var(--text-base);
  color: var(--text-primary);
}

.expand-actions {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  flex-shrink: 0;
}

.pagination-wrap {
  display: flex;
  justify-content: center;
  margin-top: var(--space-8);
}

@media (max-width: 640px) {
  .expand-content {
    flex-direction: column;
  }
  .expand-img {
    width: 100%;
  }
  .expand-actions {
    flex-direction: row;
    width: 100%;
  }
  .expand-actions .el-button {
    flex: 1;
  }
}
</style>
