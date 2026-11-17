// 员工登录态（仅 H5 代录模式用，求职者不登录）
const TOKEN_KEY = 'hr_staff_token'
const STAFF_KEY = 'hr_staff_info'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function getStaff() {
  try {
    return JSON.parse(localStorage.getItem(STAFF_KEY) || 'null')
  } catch {
    return null
  }
}

export function isLoggedIn() {
  return !!getToken()
}

export function saveLogin(token, staff) {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(STAFF_KEY, JSON.stringify(staff || {}))
}

export function clearLogin() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(STAFF_KEY)
}

export function authHeaders() {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}
