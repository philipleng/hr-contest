import axios from 'axios'
import { ElMessage } from 'element-plus'

const http = axios.create({ baseURL: '/api', timeout: 15000 })

// 请求拦截：自动带 token
http.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// 响应拦截：统一错误提示
http.interceptors.response.use(
  (res) => (res.config?.rawResponse ? res : res.data),
  async (err) => {
    let data = err.response?.data
    if (data instanceof Blob && data.type?.includes('application/json')) {
      try {
        data = JSON.parse(await data.text())
      } catch {
        data = null
      }
    }
    const msg = data?.detail || data?.message || err.message || 'Request failed.'
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('staff')
      window.location.href = `${import.meta.env.BASE_URL}login`
    }
    ElMessage.error(msg)
    return Promise.reject(err)
  }
)

export default http
