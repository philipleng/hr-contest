import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './styles/theme.css'
import en from 'element-plus/es/locale/lang/en'
import App from './App.vue'

import Login from './views/Login.vue'
import ApplicantList from './views/ApplicantList.vue'
import StaffList from './views/StaffList.vue'
import FollowUps from './views/FollowUps.vue'
import ImportBatch from './views/ImportBatch.vue'

const router = createRouter({
  // 开发环境 BASE_URL = /，生产构建 BASE_URL = /admin/
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', redirect: '/applicant' },
    { path: '/login', component: Login },
    { path: '/applicant', component: ApplicantList, meta: { requiresAuth: true } },
    { path: '/follow-ups', component: FollowUps, meta: { requiresAuth: true } },
    { path: '/import', component: ImportBatch, meta: { requiresAuth: true } },
    { path: '/staff', component: StaffList, meta: { requiresAuth: true, requiresAdmin: true } },
  ],
})

// 路由守卫：检查登录
router.beforeEach((to) => {
  const token = localStorage.getItem('token')
  if (to.meta.requiresAuth && !token) {
    return '/login'
  }
  if (to.path === '/login' && token) {
    return '/applicant'
  }
  // 员工管理仅管理员可进，普通员工直接挡回申请人列表
  if (to.meta.requiresAdmin) {
    try {
      const staff = JSON.parse(localStorage.getItem('staff') || '{}')
      if (staff.role !== 'admin') return '/applicant'
    } catch {
      return '/applicant'
    }
  }
})

const app = createApp(App)
app.use(router)
app.use(ElementPlus, { locale: en })
app.mount('#app')
