<template>
  <AdminLayout active="staff">
        <div class="page-head">
          <div>
            <h2>Staff</h2>
            <p>Manage recruiter accounts and their access to the applicant pool.</p>
          </div>
          <div class="head-actions">
            <el-button v-if="isAdmin" type="primary" @click="openCreate">Add Staff</el-button>
          </div>
        </div>

        <!-- 筛选区 -->
        <el-card class="filter-card">
          <el-form :inline="true" :model="filters" class="filter-form">
            <el-form-item label="Status">
              <el-select v-model="filters.status" placeholder="All" clearable style="width:120px">
                <el-option label="Active" value="active" />
                <el-option label="Disabled" value="disabled" />
              </el-select>
            </el-form-item>
            <el-form-item label="Role">
              <el-select v-model="filters.role" placeholder="All" clearable style="width:120px">
                <el-option label="Admin" value="admin" />
                <el-option label="Staff" value="staff" />
              </el-select>
            </el-form-item>
            <el-form-item label="Keyword">
              <el-input v-model="filters.keyword" placeholder="Username / name" clearable style="width:180px" />
            </el-form-item>
            <el-form-item class="filter-buttons">
              <el-button type="primary" @click="fetchList">Search</el-button>
              <el-button @click="resetFilters">Reset</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- 列表表格（桌面） -->
        <el-card v-if="!isMobile" class="table-card">
          <el-table :data="tableData.items" v-loading="loading">
            <el-table-column prop="id" label="ID" width="70" class-name="col-mono" />
            <el-table-column prop="username" label="Username" width="150" />
            <el-table-column prop="real_name" label="Name" min-width="150">
              <template #default="{row}">
                <span class="cell-name">{{ row.real_name }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="role" label="Role" width="100">
              <template #default="{row}">
                <span class="status-pill" :class="row.role === 'admin' ? 'is-teal' : 'is-grey'">
                  {{ row.role === 'admin' ? 'Admin' : 'Staff' }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="status" label="Status" width="110">
              <template #default="{row}">
                <span class="status-pill" :class="row.status === 'active' ? 'is-green' : 'is-grey'">
                  {{ row.status === 'active' ? 'Active' : 'Disabled' }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="Created At" width="160" class-name="col-mono">
              <template #default="{row}">
                {{ row.created_at ? row.created_at.slice(0, 19).replace('T',' ') : '' }}
              </template>
            </el-table-column>
            <el-table-column label="Actions" width="220" fixed="right">
              <template #default="{row}">
                <el-button link type="primary" size="small" @click="openEdit(row)">Edit</el-button>
                <el-button link type="warning" size="small" @click="openPassword(row)">Reset Password</el-button>
                <el-button
                  v-if="row.id !== currentStaffId"
                  link
                  :type="row.status === 'active' ? 'danger' : 'success'"
                  size="small"
                  @click="onToggleStatus(row)"
                >
                  {{ row.status === 'active' ? 'Disable' : 'Enable' }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <el-pagination
            v-model:current-page="filters.page"
            v-model:page-size="filters.page_size"
            :total="tableData.total"
            layout="total, sizes, prev, pager, next"
            :page-sizes="[10, 20, 50, 100]"
            @change="fetchList"
            style="margin-top:1rem; justify-content:flex-end"
          />
        </el-card>

        <!-- 移动端卡片列表 -->
        <template v-if="isMobile">
          <div v-loading="loading" class="mobile-list">
            <article v-for="row in tableData.items" :key="row.id" class="staff-card">
              <div class="sc-head">
                <span class="sc-avatar">{{ initials(row.real_name) }}</span>
                <div class="sc-id">
                  <div class="sc-name">{{ row.real_name }}</div>
                  <div class="sc-sub">@{{ row.username }} · ID {{ row.id }}</div>
                </div>
              </div>
              <div class="sc-meta">
                <div>
                  <span class="sc-lbl">Role</span>
                  <span class="status-pill" :class="row.role === 'admin' ? 'is-teal' : 'is-grey'">
                    {{ row.role === 'admin' ? 'Admin' : 'Staff' }}
                  </span>
                </div>
                <div>
                  <span class="sc-lbl">Status</span>
                  <span class="status-pill" :class="row.status === 'active' ? 'is-green' : 'is-grey'">
                    {{ row.status === 'active' ? 'Active' : 'Disabled' }}
                  </span>
                </div>
                <div>
                  <span class="sc-lbl">Created</span>
                  {{ row.created_at ? row.created_at.slice(0, 10) : '—' }}
                </div>
              </div>
              <div class="sc-actions">
                <el-button size="small" @click="openEdit(row)">Edit</el-button>
                <el-button size="small" @click="openPassword(row)">Reset</el-button>
                <el-button
                  v-if="row.id !== currentStaffId"
                  size="small"
                  :type="row.status === 'active' ? 'danger' : 'success'"
                  plain
                  @click="onToggleStatus(row)"
                >
                  {{ row.status === 'active' ? 'Disable' : 'Enable' }}
                </el-button>
              </div>
            </article>
            <el-empty v-if="!loading && !tableData.items.length" description="No staff" />
          </div>

          <el-pagination
            v-model:current-page="filters.page"
            :page-size="filters.page_size"
            :total="tableData.total"
            layout="prev, pager, next"
            :pager-count="5"
            small
            @change="fetchList"
            style="margin-top:1rem; justify-content:center"
          />
        </template>

    <!-- 新增/编辑员工弹窗 -->
    <el-dialog v-model="dialogVisible" :title="dialogType === 'create' ? 'Add Staff' : 'Edit Staff'" :width="isMobile ? '94%' : '420px'">
      <el-form :model="form" label-width="80px">
        <el-form-item label="Username">
          <el-input v-model="form.username" :disabled="dialogType === 'edit'" placeholder="Login name" />
        </el-form-item>
        <el-form-item label="Name">
          <el-input v-model="form.real_name" placeholder="Real name" />
        </el-form-item>
        <el-form-item v-if="dialogType === 'create'" label="Password">
          <el-input v-model="form.password" type="password" placeholder="At least 8 characters" show-password />
        </el-form-item>
        <el-form-item label="Role">
          <el-select v-model="form.role" style="width:100%">
            <el-option label="Staff" value="staff" />
            <el-option label="Admin" value="admin" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">Cancel</el-button>
        <el-button type="primary" :loading="submitting" @click="onSubmit">Confirm</el-button>
      </template>
    </el-dialog>

    <!-- 重置密码弹窗 -->
    <el-dialog v-model="passwordVisible" title="Reset Password" :width="isMobile ? '94%' : '380px'">
      <el-form :model="passwordForm" label-width="80px">
        <el-form-item label="Staff">
          <el-input :model-value="passwordForm.username" disabled />
        </el-form-item>
        <el-form-item label="New Password">
          <el-input v-model="passwordForm.password" type="password" placeholder="At least 8 characters" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="passwordVisible = false">Cancel</el-button>
        <el-button type="primary" :loading="submitting" @click="onPasswordSubmit">Confirm</el-button>
      </template>
    </el-dialog>
  </AdminLayout>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AdminLayout from '../components/AdminLayout.vue'
import { useIsMobile } from '../composables/useIsMobile'
import http from '../api/http'

const isMobile = useIsMobile()
const currentStaffId = computed(() => {
  try { return JSON.parse(localStorage.getItem('staff') || '{}').id || 0 } catch { return 0 }
})
const isAdmin = computed(() => {
  try { return JSON.parse(localStorage.getItem('staff') || '{}').role === 'admin' } catch { return false }
})

// 头像取姓名首字母
function initials(name) {
  const parts = String(name || '').trim().split(/\s+/)
  return ((parts[0] || '?')[0] + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase()
}

// 列表数据
const loading = ref(false)
const filters = reactive({ status: '', role: '', keyword: '', page: 1, page_size: 20 })
const tableData = reactive({ total: 0, items: [] })

async function fetchList() {
  loading.value = true
  try {
    const params = {
      page: filters.page,
      page_size: filters.page_size,
      status: filters.status || undefined,
      role: filters.role || undefined,
      keyword: filters.keyword || undefined,
    }
    const res = await http.get('/staff/list', { params })
    tableData.total = res.data.total
    tableData.items = res.data.items
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  Object.assign(filters, { status: '', role: '', keyword: '', page: 1, page_size: 20 })
  fetchList()
}

// 新增/编辑
const dialogVisible = ref(false)
const dialogType = ref('create')
const submitting = ref(false)
const form = reactive({ id: 0, username: '', real_name: '', password: '', role: 'staff' })

function openCreate() {
  dialogType.value = 'create'
  Object.assign(form, { id: 0, username: '', real_name: '', password: '', role: 'staff' })
  dialogVisible.value = true
}

function openEdit(row) {
  dialogType.value = 'edit'
  Object.assign(form, { id: row.id, username: row.username, real_name: row.real_name, role: row.role })
  dialogVisible.value = true
}

async function onSubmit() {
  if (!form.real_name) {
    ElMessage.warning('Please enter a name.')
    return
  }
  if (dialogType.value === 'create') {
    if (!form.username || !form.password) {
      ElMessage.warning('Please enter username and password.')
      return
    }
    if (form.password.length < 8) {
      ElMessage.warning('Password must be at least 8 characters.')
      return
    }
  }
  submitting.value = true
  try {
    if (dialogType.value === 'create') {
      await http.post('/staff', form)
      ElMessage.success('Created.')
    } else {
      await http.patch(`/staff/${form.id}`, { real_name: form.real_name, role: form.role })
      ElMessage.success('Updated.')
    }
    dialogVisible.value = false
    fetchList()
  } finally {
    submitting.value = false
  }
}

// 重置密码
const passwordVisible = ref(false)
const passwordForm = reactive({ id: 0, username: '', password: '' })

function openPassword(row) {
  Object.assign(passwordForm, { id: row.id, username: row.username, password: '' })
  passwordVisible.value = true
}

async function onPasswordSubmit() {
  if (!passwordForm.password || passwordForm.password.length < 8) {
    ElMessage.warning('Password must be at least 8 characters.')
    return
  }
  submitting.value = true
  try {
    await http.patch(`/staff/${passwordForm.id}/password`, { password: passwordForm.password })
    ElMessage.success('Password reset.')
    passwordVisible.value = false
  } finally {
    submitting.value = false
  }
}

// 停用/启用
async function onToggleStatus(row) {
  const isDisabling = row.status === 'active'
  try {
    await ElMessageBox.confirm(
      `Are you sure you want to ${isDisabling ? 'disable' : 'enable'} "${row.real_name}"?`,
      'Confirm',
      {
        confirmButtonText: 'Confirm',
        cancelButtonText: 'Cancel',
        type: 'warning',
      },
    )
    await http.patch(`/staff/${row.id}/status`, { status: row.status === 'active' ? 'disabled' : 'active' })
    ElMessage.success(isDisabling ? 'Staff disabled.' : 'Staff enabled.')
    fetchList()
  } catch (e) {
    // 用户取消
  }
}

onMounted(() => { fetchList() })
</script>

<style scoped>
.filter-card { margin-bottom: 14px; }
.filter-form :deep(.el-form-item) { margin-right: 14px; margin-bottom: 0; }
.filter-buttons :deep(.el-button + .el-button) { margin-left: 0; }
.filter-buttons :deep(.el-form-item__content) { gap: 8px; }
.table-card :deep(.el-card__body) { padding: 0 0 12px; }
.table-card :deep(.el-pagination) { padding: 0 16px; }
.cell-name { font-weight: 600; color: var(--ap-ink); }
:deep(.el-table__cell .el-button.is-link) { font-size: 11.5px; font-weight: 600; }
:deep(.el-table__cell .el-button.is-link + .el-button.is-link) { margin-left: 8px; }

.mobile-list { min-height: 120px; }
.staff-card {
  background: var(--ap-surface);
  border: 1px solid var(--ap-rule);
  border-radius: 12px;
  padding: 12px;
  margin-bottom: 10px;
  box-shadow: var(--ap-shadow);
}
.sc-head { display: flex; align-items: center; gap: 10px; }
.sc-avatar {
  width: 36px; height: 36px; border-radius: 50%;
  background: var(--ap-teal-soft); color: var(--ap-teal);
  font-size: 11px; font-weight: 700; text-transform: uppercase;
  display: inline-flex; align-items: center; justify-content: center;
  flex: 0 0 auto;
}
.sc-id { min-width: 0; flex: 1; }
.sc-name {
  font-size: 14px; font-weight: 700; color: var(--ap-ink);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.sc-sub { font-size: 9.5px; color: var(--ap-muted); margin-top: 2px; }
.sc-meta {
  display: grid;
  grid-template-columns: 1fr 1fr auto;
  align-items: center;
  gap: 8px 10px;
  margin: 11px 0 10px;
  padding: 10px 0;
  border-top: 1px solid var(--ap-rule-soft);
  border-bottom: 1px solid var(--ap-rule-soft);
  font-size: 11.5px;
  color: var(--ap-ink-soft);
}
.sc-lbl {
  display: block;
  font-size: 8.5px;
  color: var(--ap-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 3px;
}
.sc-actions { display: flex; gap: 7px; flex-wrap: wrap; }
.sc-actions :deep(.el-button) { flex: 1 1 30%; margin-left: 0; }

@media (max-width: 900px) {
  .filter-form :deep(.el-form-item) {
    display: block;
    width: 100%;
    margin-right: 0;
    margin-bottom: 10px;
  }
  .filter-form :deep(.el-form-item__content) { width: 100%; }
  .filter-form :deep(.el-input),
  .filter-form :deep(.el-select),
  .filter-form :deep(.el-date-editor) { width: 100% !important; }
  .filter-buttons :deep(.el-form-item__content) {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
  .filter-buttons :deep(.el-button) { flex: 1 1 45%; margin-left: 0; }
}
</style>
