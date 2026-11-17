<template>
  <div class="admin-layout">
    <header class="topbar">
      <button class="menu-btn" type="button" aria-label="Open navigation" @click="navVisible = true">
        <el-icon><Expand /></el-icon>
      </button>

      <div class="brand">
        <span class="brand-mark">HR</span>
        <span class="brand-text">
          <strong>Applicant Pool</strong>
          <small>Recruitment admin</small>
        </span>
      </div>

      <div class="top-right">
        <span class="avatar-sm">{{ initials }}</span>
        <span class="who">{{ staffName }} · <b>{{ roleLabel }}</b></span>
        <button class="logout" type="button" @click="onLogout">Sign out</button>
      </div>
    </header>

    <div class="shell">
      <aside class="sidebar">
        <p class="side-label">Workspace</p>
        <el-menu :default-active="active" class="nav-menu">
          <el-menu-item index="applicant" @click="go('/applicant')">
            <el-icon><Grid /></el-icon>
            <span>Applicants</span>
          </el-menu-item>
          <el-menu-item index="follow-ups" @click="go('/follow-ups')">
            <el-icon><Bell /></el-icon>
            <span>Follow-ups</span>
          </el-menu-item>
          <el-menu-item index="import" @click="go('/import')">
            <el-icon><Upload /></el-icon>
            <span>Batch Import</span>
          </el-menu-item>
          <el-menu-item v-if="isAdmin" index="staff" @click="go('/staff')">
            <el-icon><User /></el-icon>
            <span>Staff</span>
          </el-menu-item>
        </el-menu>
      </aside>

      <main class="content">
        <slot />
      </main>
    </div>

    <!-- 移动端导航：侧边栏收进抽屉 -->
    <el-drawer v-model="navVisible" class="nav-drawer" direction="ltr" size="248px" :with-header="false">
      <div class="drawer-head">
        <span class="brand-mark">HR</span>
        <span class="brand-text">
          <strong>Applicant Pool</strong>
          <small>Recruitment admin</small>
        </span>
      </div>
      <el-menu :default-active="active" class="nav-menu drawer-menu">
        <el-menu-item index="applicant" @click="go('/applicant')">
          <el-icon><Grid /></el-icon>
          <span>Applicants</span>
        </el-menu-item>
        <el-menu-item index="follow-ups" @click="go('/follow-ups')">
          <el-icon><Bell /></el-icon>
          <span>Follow-ups</span>
        </el-menu-item>
        <el-menu-item index="import" @click="go('/import')">
          <el-icon><Upload /></el-icon>
          <span>Batch Import</span>
        </el-menu-item>
        <el-menu-item v-if="isAdmin" index="staff" @click="go('/staff')">
          <el-icon><User /></el-icon>
          <span>Staff</span>
        </el-menu-item>
      </el-menu>
      <div class="drawer-foot">
        <span class="avatar-sm">{{ initials }}</span>
        <span class="drawer-user">
          <strong>{{ staffName }}</strong>
          <small>{{ roleLabel }}</small>
        </span>
        <el-button text size="small" @click="onLogout">Sign out</el-button>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Expand, Grid, User, Bell, Upload } from '@element-plus/icons-vue'

defineProps({
  active: { type: String, required: true },
})

const router = useRouter()
const navVisible = ref(false)

const staff = computed(() => {
  try {
    return JSON.parse(localStorage.getItem('staff') || '{}')
  } catch {
    return {}
  }
})

const staffName = computed(() => staff.value.real_name || 'Admin')
const isAdmin = computed(() => staff.value.role === 'admin')
const roleLabel = computed(() => (isAdmin.value ? 'Admin' : 'Staff'))
// 头像用姓名首字母，避免引入额外图片资源
const initials = computed(() => {
  const parts = String(staffName.value).trim().split(/\s+/)
  return (parts[0]?.[0] || 'A') + (parts.length > 1 ? parts[parts.length - 1][0] : '')
})

function go(path) {
  navVisible.value = false
  if (router.currentRoute.value.path !== path) router.push(path)
}

function onLogout() {
  localStorage.removeItem('token')
  localStorage.removeItem('staff')
  router.push('/login')
}
</script>

<style scoped>
.admin-layout {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--ap-canvas);
}

/* 顶栏 */
.topbar {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 18px;
  height: 62px;
  padding: 0 24px;
  background: var(--ap-surface);
  border-bottom: 1px solid var(--ap-rule);
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.brand-mark {
  width: 32px;
  height: 32px;
  border-radius: 9px;
  background: var(--ap-teal);
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.02em;
  flex: 0 0 auto;
}

.brand-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.brand-text strong {
  font-size: 13.5px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--ap-ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.brand-text small {
  font-size: 10px;
  color: var(--ap-muted);
  margin-top: 1px;
  white-space: nowrap;
}

.top-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 10px;
  white-space: nowrap;
}

.avatar-sm {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #dcece7;
  color: var(--ap-teal);
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
}

.who {
  font-size: 11.5px;
  color: var(--ap-ink-soft);
}

.who b {
  color: var(--ap-ink);
  font-weight: 600;
}

.logout {
  background: none;
  border: 0;
  padding: 4px 2px;
  color: var(--ap-muted);
  font-size: 11.5px;
  cursor: pointer;
}

.logout:hover {
  color: var(--ap-teal);
}

.menu-btn {
  display: none;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border: 1px solid var(--ap-rule);
  border-radius: 9px;
  background: var(--ap-surface);
  color: var(--ap-teal);
  font-size: 16px;
  cursor: pointer;
  flex: 0 0 auto;
}

/* 主体 */
.shell {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 208px 1fr;
}

.sidebar {
  background: var(--ap-surface);
  border-right: 1px solid var(--ap-rule);
  padding: 18px 12px;
}

.side-label {
  margin: 0 0 8px;
  padding: 0 10px;
  font-size: 9px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ap-muted);
}

.nav-menu {
  border-right: none;
  background: transparent;
}

.nav-menu :deep(.el-menu-item) {
  height: 38px;
  line-height: 38px;
  margin-bottom: 2px;
  padding-left: 10px !important;
  border-radius: 8px;
  font-size: 12.5px;
  color: var(--ap-ink-soft);
}

.nav-menu :deep(.el-menu-item .el-icon) {
  font-size: 15px;
  margin-right: 9px;
}

.nav-menu :deep(.el-menu-item:hover) {
  background: #f2f7f5;
  color: var(--ap-ink);
}

.nav-menu :deep(.el-menu-item.is-active) {
  background: var(--ap-teal-soft);
  color: var(--ap-teal);
  font-weight: 600;
}

.content {
  min-width: 0;
  padding: 22px 24px 28px;
}

/* 移动端抽屉 */
.drawer-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 16px 14px;
  border-bottom: 1px solid var(--ap-rule);
  margin-bottom: 10px;
}

.drawer-menu {
  padding: 0 10px;
}

.drawer-foot {
  margin-top: auto;
  padding: 14px 16px 20px;
  border-top: 1px solid var(--ap-rule);
  display: flex;
  align-items: center;
  gap: 10px;
}

.drawer-user {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.drawer-user strong {
  font-size: 12px;
  color: var(--ap-ink);
}

.drawer-user small {
  font-size: 10px;
  color: var(--ap-muted);
  margin-top: 1px;
}

@media (max-width: 900px) {
  .topbar {
    height: 56px;
    padding: 0 14px;
    gap: 10px;
  }

  .brand {
    order: 1;
  }

  .menu-btn {
    display: inline-flex;
    order: 2;
    margin-left: auto;
  }

  .top-right {
    display: none;
  }

  .shell {
    display: block;
  }

  .sidebar {
    display: none;
  }

  .content {
    padding: 14px 12px 22px;
  }
}
</style>
