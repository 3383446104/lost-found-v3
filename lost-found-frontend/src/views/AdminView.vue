<template>
  <div class="page-container">
    <h1 class="page-title">管理面板</h1>

    <el-tabs v-model="activeTab" type="border-card">
      <!-- ====== 物品管理 Tab（合并原审核+管理） ====== -->
      <el-tab-pane label="物品管理" name="review">
        <!-- 筛选行 -->
        <div class="item-filter-row">
          <el-input v-model="itemFilter.keyword" placeholder="搜索标题..." clearable size="small" style="width:180px" @input="onItemFilterChange" @clear="onItemFilterChange">
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
          <el-select v-model="itemFilter.review" placeholder="审核" size="small" style="width:110px" @change="onItemFilterChange" clearable>
            <el-option label="待审核" value="pending" />
            <el-option label="已通过" value="approved" />
            <el-option label="已驳回" value="rejected" />
          </el-select>
          <el-select v-model="itemFilter.status" placeholder="状态" size="small" style="width:110px" @change="onItemFilterChange" clearable>
            <el-option label="展示中" value="active" />
            <el-option label="待审核" value="pending" />
            <el-option label="已找回/已归还" value="claimed" />
            <el-option label="已关闭" value="closed" />
            <el-option label="已驳回" value="rejected" />
          </el-select>
          <el-select v-model="itemFilter.type" placeholder="类型" size="small" style="width:90px" @change="onItemFilterChange" clearable>
            <el-option label="失物" value="lost" />
            <el-option label="拾物" value="found" />
          </el-select>
          <span v-if="total" class="item-count">共 {{ total }} 条</span>
        </div>

        <!-- 批量操作工具栏 -->
        <div v-if="items.length && !loading" class="batch-toolbar">
          <el-button type="success" size="small" :disabled="selectedIds.length===0" @click="handleBatch('approve')" :loading="batchLoading">
            批量通过 ({{ selectedIds.length }})
          </el-button>
          <el-button type="warning" size="small" :disabled="selectedIds.length===0" @click="handleBatch('close')" :loading="batchLoading">
            批量关闭
          </el-button>
          <el-button type="danger" size="small" :disabled="selectedIds.length===0" @click="handleBatch('delete')" :loading="batchLoading" plain>
            批量删除
          </el-button>
        </div>

        <el-empty v-if="items.length === 0 && !loading" :description="itemFilter.review==='pending'||!itemFilter.review?'暂无物品':'未找到匹配物品'" />

        <div v-else class="review-table-wrap">
          <el-table :data="items" style="width:100%" stripe row-key="id" @selection-change="handleSelectionChange">
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
                    <div class="expand-field"><span class="field-label">描述</span><span class="field-value">{{ row.description || '无描述' }}</span></div>
                    <div class="expand-field"><span class="field-label">位置</span><span class="field-value">{{ row.location || '未填写' }}</span></div>
                    <div class="expand-field"><span class="field-label">联系方式</span><span class="field-value">{{ row.contact || '未填写' }}</span></div>
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="id" label="ID" width="60" align="center" />
            <el-table-column prop="title" label="标题" min-width="160">
              <template #default="{ row }"><router-link :to="`/items/${row.id}`" class="item-link">{{ row.title }}</router-link></template>
            </el-table-column>
            <el-table-column prop="type" label="类型" width="80" align="center">
              <template #default="{ row }"><span class="status-tag" :style="{background:ITEM_TYPE_MAP[row.type]?.bg,color:ITEM_TYPE_MAP[row.type]?.color}">{{ ITEM_TYPE_MAP[row.type]?.label }}</span></template>
            </el-table-column>
            <el-table-column prop="review_status" label="审核" width="80" align="center">
              <template #default="{ row }">
                <span v-if="row.review_status==='pending'" style="color:#FF9800">待审核</span>
                <span v-else-if="row.review_status==='approved'" style="color:#4CAF50">已通过</span>
                <span v-else style="color:#E57373">已驳回</span>
              </template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="80" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.status==='active'" type="success" size="small">展示中</el-tag>
                <el-tag v-else-if="row.status==='pending'" type="warning" size="small">待审核</el-tag>
                <el-tag v-else-if="row.status==='claimed'" type="info" size="small">{{ row.type === 'lost' ? '已找回' : '已归还' }}</el-tag>
                <el-tag v-else size="small">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="时间" width="160" />
            <el-table-column label="操作" width="200" align="center" fixed="right">
              <template #default="{ row }">
                <template v-if="row.review_status==='pending'">
                  <el-button type="success" size="small" @click="approve(row.id)">通过</el-button>
                  <el-button type="danger" size="small" @click="reject(row.id)" plain>驳回</el-button>
                </template>
                <template v-else>
                  <el-dropdown @command="(cmd) => handleStatusChange(row, cmd)">
                    <el-button size="small">改状态<el-icon><ArrowDown /></el-icon></el-button>
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item command="active" v-if="row.status!=='active'">设为展示中</el-dropdown-item>
                        <el-dropdown-item command="closed" v-if="row.status!=='closed'">关闭</el-dropdown-item>
                        <el-dropdown-item command="claimed" v-if="row.status!=='claimed'">{{ row.type === 'lost' ? '标记已找回' : '标记已归还' }}</el-dropdown-item>
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                </template>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <div v-if="total > pageSize" class="pagination-wrap">
          <el-pagination v-model:current-page="page" :page-size="pageSize" :total="total" layout="prev, pager, next" @current-change="loadItems" />
        </div>

        <!-- 驳回对话框 -->
        <el-dialog v-model="dialogVisible" title="驳回物品" width="440px" :close-on-click-modal="false">
          <el-form label-position="top">
            <el-form-item label="驳回理由（必填）">
              <el-input v-model="reason" type="textarea" :rows="4" placeholder="请填写驳回理由..." maxlength="200" show-word-limit />
            </el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="dialogVisible=false">取消</el-button>
            <el-button type="danger" @click="confirmReject" :loading="rejecting">确认驳回</el-button>
          </template>
        </el-dialog>
      </el-tab-pane>

      <!-- ====== 用户管理 Tab ====== -->
      <el-tab-pane label="用户管理" name="users">
        <div style="margin-bottom:12px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          <el-button type="primary" size="small" @click="openCreateUserDialog">
            <el-icon><Plus /></el-icon>新增用户
          </el-button>
          <el-input v-model="userKeyword" placeholder="搜索用户名/手机/邮箱..." clearable size="small" style="width:260px" @input="onUserSearch" @clear="onUserSearch">
            <template #prefix>
              <el-icon v-if="!userSearching"><Search /></el-icon>
              <el-icon v-else class="is-loading"><Loading /></el-icon>
            </template>
          </el-input>
          <el-switch v-model="showDeletedUsers" size="small" active-text="含已注销" @change="onUserSearch" />
          <span v-if="userKeyword.trim() && !userSearching" class="search-result-hint">
            找到 {{ userTotal }} 条结果
          </span>
        </div>
        <div v-loading="userLoading">
          <el-empty v-if="!userLoading && userKeyword.trim() && users.length === 0" description="未找到匹配的用户" />
          <el-table v-else :data="users" stripe style="width:100%" :row-class-name="rowClassName">
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column prop="username" label="用户名" min-width="140" />
            <el-table-column prop="role" label="角色" width="110">
              <template #default="{ row }">
                <el-tag v-if="row.role==='admin'" type="success" size="small">管理员</el-tag>
                <el-tag v-else-if="row.role==='disabled'" type="danger" size="small">已禁用</el-tag>
                <el-tag v-else-if="row.role==='deleted'" type="info" size="small">已注销</el-tag>
                <el-tag v-else size="small">用户</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="phone" label="手机号" width="130" />
            <el-table-column prop="email" label="邮箱" min-width="160" />
            <el-table-column prop="created_at" label="注册时间" width="170" />
            <el-table-column label="操作" width="110" align="center">
              <template #default="{ row }">
                <template v-if="row.role !== 'deleted'">
                  <el-dropdown @command="(cmd) => handleUserAction(row, cmd)" trigger="click">
                    <el-button size="small">操作 <el-icon><ArrowDown /></el-icon></el-button>
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item command="set-admin" v-if="row.role==='user'">
                          <el-icon><Select /></el-icon>设为管理员
                        </el-dropdown-item>
                        <el-dropdown-item command="unset-admin" v-if="row.role==='admin'">
                          <el-icon><CloseBold /></el-icon>取消管理员
                        </el-dropdown-item>
                        <el-dropdown-item command="disable" v-if="row.role==='user'||row.role==='admin'">
                          <el-icon><Remove /></el-icon>禁用账号
                        </el-dropdown-item>
                        <el-dropdown-item command="enable" v-if="row.role==='disabled'">
                          <el-icon><CircleCheck /></el-icon>启用账号
                        </el-dropdown-item>
                        <el-dropdown-item command="delete" divided style="color:var(--el-color-danger)">
                          <el-icon><Delete /></el-icon>删除用户
                        </el-dropdown-item>
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                </template>
                <span v-else class="deleted-hint">—</span>
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
            <el-table-column prop="target_role" label="范围" width="90">
              <template #default="{ row }">{{ row.target_role==='all'?'全体':row.target_role==='user'?'用户':'管理' }}</template>
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
import { getPendingItems, reviewItem, batchApprove, getUsers, updateUser, createUser, deleteUser, getAllItems, updateItemStatus, batchItems } from '@/api/admin'
import { getAnnouncements, createAnnouncement, updateAnnouncement, deleteAnnouncement } from '@/api/announcements'
import { getImageUrl, ITEM_TYPE_MAP } from '@/utils/helpers'
import { ElMessage, ElMessageBox } from 'element-plus'
import { PictureFilled, Select, CloseBold, Plus, Edit, Search, Loading, ArrowDown, Remove, CircleCheck, Delete } from '@element-plus/icons-vue'

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
const userKeyword = ref('')
const userSearching = ref(false)
const showDeletedUsers = ref(false)
let userSearchTimer = null
const createUserVisible = ref(false)
const creatingUser = ref(false)
const newUserForm = ref({ username: '', password: '', phone: '', email: '', role: 'user' })

// 物品筛选
const itemFilter = ref({ keyword: '', review: 'pending', status: '', type: '' })
let itemFilterTimer = null

const loadItems = async () => {
  loading.value = true
  try {
    const f = itemFilter.value
    const params = { page: page.value, size: pageSize.value }
    if (f.keyword.trim()) params.keyword = f.keyword.trim()
    if (f.review) params.review = f.review
    if (f.status) params.item_status = f.status
    if (f.type) params.item_type = f.type
    const res = await getAllItems(params)
    items.value = res.items || []
    total.value = res.total || 0
  } catch (e) {
    console.error('加载物品列表失败', e)
  } finally { loading.value = false }
}

const onItemFilterChange = () => {
  clearTimeout(itemFilterTimer)
  itemFilterTimer = setTimeout(() => { page.value = 1; loadItems() }, 300)
}

const handleStatusChange = async (row, status) => {
  try {
    await updateItemStatus(row.id, status)
    ElMessage.success(`状态已变更`)
    loadItems()
  } catch { }
}

const handleBatch = async (action) => {
  const label = { approve: '批量通过', close: '批量关闭', delete: '批量删除' }[action]
  try {
    if (action === 'delete') {
      await ElMessageBox.confirm(`确认删除已选的 ${selectedIds.value.length} 件物品？此操作不可恢复。`, label, { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'error' })
    }
    batchLoading.value = true
    const res = await batchItems({ ids: selectedIds.value, action })
    ElMessage.success(`${label}完成，影响 ${res.count || selectedIds.value.length} 条`)
    selectedIds.value = []
    loadItems()
  } catch { } finally { batchLoading.value = false }
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

const onUserSearch = () => {
  userSearching.value = true
  clearTimeout(userSearchTimer)
  userSearchTimer = setTimeout(() => {
    userPage.value = 1
    loadUsers().finally(() => { userSearching.value = false })
  }, 300)
}

const loadUsers = async () => {
  userLoading.value = true
  try {
    const res = await getUsers(userPage.value, userPageSize.value, userKeyword.value.trim(), showDeletedUsers.value)
    users.value = res.users || []
    userTotal.value = res.total || 0
  } catch { } finally { userLoading.value = false }
}

const handleUserAction = (row, cmd) => {
  if (cmd === 'set-admin') setUserRole(row.id, 'admin')
  else if (cmd === 'unset-admin') setUserRole(row.id, 'user')
  else if (cmd === 'disable' || cmd === 'enable') toggleUser(row.id)
  else if (cmd === 'delete') handleDeleteUser(row)
}

const setUserRole = async (id, role) => {
  try {
    await updateUser(id, { action: 'set_role', role })
    ElMessage.success(`已${role === 'admin' ? '设为管理员' : '取消管理员'}`)
    loadUsers()
  } catch { }
}

const toggleUser = async (id) => {
  try {
    await updateUser(id, { action: 'toggle_status' })
    ElMessage.success('用户状态已更新')
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
const annForm = ref({ title: '', content: '', is_pinned: false, target_role: 'all' })

const loadAnnouncements = async () => {
  annLoading.value = true
  try { const r = await getAnnouncements(true); announcements.value = r.announcements || [] } catch { } finally { annLoading.value = false }
}

const openAnnDialog = (row) => {
  editingAnn.value = row || null
  annForm.value = row ? { title: row.title, content: row.content, is_pinned: !!row.is_pinned, target_role: row.target_role || 'all' } : { title: '', content: '', is_pinned: false, target_role: 'all' }
  annDialogVisible.value = true
}

const handleSaveAnn = async () => {
  if (!annForm.value.title.trim() || !annForm.value.content.trim()) { ElMessage.warning('标题和内容为必填'); return }
  annSaving.value = true
  try {
    const data = { title: annForm.value.title.trim(), content: annForm.value.content.trim(), is_pinned: annForm.value.is_pinned ? 1 : 0, target_role: annForm.value.target_role }
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

const rowClassName = ({ row }) => row.role === 'deleted' ? 'row-deleted' : ''

onMounted(() => { loadItems(); loadUsers(); loadAnnouncements() })
</script>

<style scoped>
.item-filter-row {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: var(--space-3);
}
.item-count {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
  margin-left: auto;
}

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

:deep(.row-deleted) {
  opacity: 0.45;
  pointer-events: none;
}

.search-result-hint {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
  white-space: nowrap;
}

.deleted-hint {
  color: var(--text-muted);
  font-size: var(--text-sm);
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
