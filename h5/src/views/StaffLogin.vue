<template>
  <div class="login-page">
    <header class="masthead">
      <div class="masthead-inner">
        <p class="masthead-note">For HR staff doing field intake</p>
        <h1>Staff sign in</h1>
      </div>
    </header>

    <van-cell-group inset class="section">
      <van-field
        v-model="username"
        label="Username"
        placeholder="Your staff account"
        autocomplete="username"
      />
      <van-field
        v-model="password"
        type="password"
        label="Password"
        placeholder="Your password"
        autocomplete="current-password"
        @keyup.enter="onLogin"
      />
    </van-cell-group>

    <div class="submit-area">
      <van-button
        type="primary"
        size="large"
        block
        :loading="loading"
        @click="onLogin"
      >
        {{ loading ? 'Signing in...' : 'Sign in' }}
      </van-button>
      <p class="hint">Applicants do not need to sign in.</p>
      <p class="hint">
        <a @click.prevent="$router.replace('/apply')">Back to application form</a>
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showFailToast, showSuccessToast } from 'vant'
import axios from 'axios'
import { saveLogin } from '../auth'

const route = useRoute()
const router = useRouter()

const username = ref('')
const password = ref('')
const loading = ref(false)

async function onLogin() {
  if (!username.value || !password.value) {
    showFailToast('Enter your username and password')
    return
  }
  loading.value = true
  try {
    const res = await axios.post('/api/auth/login', {
      username: username.value.trim(),
      password: password.value,
    })
    saveLogin(res.data.data.token, res.data.data.staff)
    showSuccessToast('Signed in')
    // 只允许站内相对路径，避免 ?redirect= 被用来做开放重定向
    const redirect = typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/')
      ? route.query.redirect
      : '/apply'
    router.replace(redirect)
  } catch (err) {
    const status = err.response?.status
    if (status === 401) {
      showFailToast('Wrong username or password')
    } else if (status === 403) {
      showFailToast('This account has been disabled')
    } else if (status === 429) {
      showFailToast('Too many attempts, please try again in a minute')
    } else {
      showFailToast('Network error, please try again')
    }
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  max-width: 560px;
  margin: 0 auto;
  min-height: 100vh;
  box-sizing: border-box;
}
.masthead {
  padding: 2.25rem 1.25rem 1rem;
}
.masthead-inner {
  border-bottom: 3px double var(--rule);
  padding-bottom: 1.1rem;
}
.masthead-note {
  margin: 0 0 0.3rem;
  font-size: 0.78rem;
  color: var(--ink-faint);
}
h1 {
  margin: 0;
  font-family: var(--serif);
  font-size: 1.8rem;
  font-weight: 600;
  line-height: 1.15;
  color: var(--teal);
}
.section {
  margin-top: 1.5rem;
}
.submit-area {
  padding: 1.5rem 1rem;
}
.hint {
  margin-top: 1rem;
  text-align: center;
  font-size: 0.85rem;
  line-height: 1.6;
  color: var(--ink-faint);
}
.hint a {
  color: var(--teal);
  text-decoration: underline;
  text-underline-offset: 2px;
}
</style>
