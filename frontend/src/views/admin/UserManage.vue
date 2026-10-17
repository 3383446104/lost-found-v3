<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">用户管理</h1>
        <p class="page-desc">管理用户账号：角色、禁用/启用、注销</p>
      </div>
    </div>

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
            <el-tag v-else-if="row.status==='disabled'" type="danger" size="small">已禁用</el-tag>
            <el-tag v-else-if="row.status==='deleted'" type="info" size="small">已注销</el-tag>
            <el-tag v-else size="small">用户</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="phone" label="手机号" width="130" />
        <el-table-column prop="email" label="邮箱" min-width="160" />
        <el-table-column prop="created_at" label="注册时间" width="170" />
        <el-table-column label="操作" width="110" align="center">
          <template #default="{ row }">
            <template v-if="row.status !== 'deleted'">
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
                    <el-dropdown-item command="disable" v-if="row.status==='active'">
                      <el-icon><Remove /></el-icon>禁用账号
                    </el-dropdown-item>
                    <el-dropdown-item command="enable" v-if="row.status==='disabled'">
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
import { getUsers, updateUser, createUser, deleteUser } from '@/api/admin'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, Loading, ArrowDown, Select, CloseBold, Remove, CircleCheck, Delete } from '@element-plus/icons-vue'

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

const rowClassName = ({ row }) => row.status === 'deleted' ? 'row-deleted' : ''

onMounted(loadUsers)
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

.search-result-hint {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
  white-space: nowrap;
}

.deleted-hint {
  color: var(--text-muted);
  font-size: var(--text-sm);
}

:deep(.row-deleted) {
  opacity: 0.45;
  pointer-events: none;
}
</style>
