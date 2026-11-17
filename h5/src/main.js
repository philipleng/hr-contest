import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import Vant, { Locale } from 'vant'
import enUS from 'vant/es/locale/lang/en-US'
import 'vant/lib/index.css'
import App from './App.vue'

import ApplyForm from './views/ApplyForm.vue'
import ApplySuccess from './views/ApplySuccess.vue'
import StaffLogin from './views/StaffLogin.vue'

// 申请人全部为菲律宾本地用户，Vant 默认中文（确定/取消）必须切到英文
Locale.use('en-US', enUS)

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/apply' },
    { path: '/apply', component: ApplyForm },
    { path: '/apply/success', component: ApplySuccess },
    { path: '/staff/login', component: StaffLogin },
  ],
})

const app = createApp(App)
app.use(router)
app.use(Vant)
app.mount('#app')
