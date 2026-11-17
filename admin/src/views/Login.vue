<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-brand"><span class="brand-mark">HR</span></div>
      <h2>Applicant Pool</h2>
      <p class="subtitle">Sign in to the recruitment admin</p>

      <el-form :model="form" @submit.prevent="onLogin">
        <el-form-item>
          <el-input v-model="form.username" placeholder="Username" size="large" prefix-icon="User" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="form.password" type="password" placeholder="Password" size="large" prefix-icon="Lock" show-password @keyup.enter="onLogin" />
        </el-form-item>
        <el-button type="primary" size="large" class="login-btn" :loading="loading" @click="onLogin">Sign in</el-button>
      </el-form>

      <p class="login-hint">For HR staff only. Applicants do not need to sign in.</p>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import http from '../api/http'

const router = useRouter()
const loading = ref(false)
const form = reactive({ username: '', password: '' })

async function onLogin() {
  if (!form.username || !form.password) {
    ElMessage.warning('Please enter username and password.')
    return
  }
  loading.value = true
  try {
    const res = await http.post('/auth/login', form)
    localStorage.setItem('token', res.data.token)
    localStorage.setItem('staff', JSON.stringify(res.data.staff))
    ElMessage.success('Logged in.')
    router.push('/applicant')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  background: var(--ap-canvas);
}

.login-card {
  width: 380px;
  max-width: 100%;
  background: var(--ap-surface);
  border: 1px solid var(--ap-rule);
  border-radius: 16px;
  padding: 32px 28px 24px;
  box-shadow: 0 1px 2px rgba(20, 40, 36, 0.04), 0 18px 48px rgba(20, 40, 36, 0.08);
}

.login-brand {
  display: flex;
  justify-content: center;
  margin-bottom: 14px;
}

.brand-mark {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: var(--ap-teal);
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.02em;
}

h2 {
  text-align: center;
  margin: 0 0 4px;
  font-size: 19px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--ap-ink);
}

.subtitle {
  text-align: center;
  color: var(--ap-muted);
  font-size: 11.5px;
  margin: 0 0 22px;
}

:deep(.el-form-item) {
  margin-bottom: 14px;
}

.login-btn {
  width: 100%;
  margin-top: 2px;
}

.login-hint {
  text-align: center;
  color: var(--ap-muted);
  font-size: 10.5px;
  line-height: 1.6;
  margin: 18px 0 0;
}
</style>
