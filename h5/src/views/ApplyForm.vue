<template>
  <div class="apply-page">
    <!-- 顶部标题 -->
    <header class="masthead">
      <div class="masthead-inner">
        <p class="masthead-note">{{ isStaff ? 'Staff-assisted intake' : 'Manila recruitment pool' }}</p>
        <p v-if="isStaff && staff?.real_name" class="masthead-note">Recording for {{ staff.real_name }}</p>
        <h1>Job <mark>application</mark></h1>
        <p class="lead">
          Please fill in as much detail as you can — the more you tell us, the better your
          chances of getting the job. It takes about 3 minutes.
        </p>
        <p v-if="sourceRef" class="ref-tag">Referral code: {{ sourceRef }}</p>
      </div>
    </header>

    <!-- 员工登录条 -->
    <div class="staff-bar">
      <template v-if="isStaff">
        <span>Signed in as {{ staff?.real_name || staff?.username }}</span>
        <a @click.prevent="onLogout">Sign out</a>
      </template>
      <template v-else>
        <span>For HR staff only. Applicants do not need to sign in.</span>
        <a @click.prevent="goStaffLogin">Staff sign in</a>
      </template>
    </div>

    <!-- 隐私同意 -->
    <van-cell-group inset class="section consent">
      <van-checkbox v-model="form.privacy_agreed" shape="square">
        <span class="privacy-text">
          I agree to the collection and processing of my personal data (including photo and video)
          for recruitment purposes under the Data Privacy Act of 2012 (RA 10173).
        </span>
      </van-checkbox>
    </van-cell-group>

    <!-- A. 基本信息 -->
    <van-cell-group inset class="section" title="Basic Information">
      <van-field v-model="form.first_name" label="First Name" placeholder="Juan" required />
      <van-field v-model="form.middle_name" label="Middle Name" placeholder="Santos (optional)" />
      <van-field v-model="form.last_name" label="Last Name" placeholder="Dela Cruz" required />

      <van-field label="Gender" readonly is-link :model-value="genderText" @click="showGender = true" />
      <van-popup v-model:show="showGender" position="bottom" round>
        <van-picker :columns="genderOptions" :model-value="genderPickerValue" @confirm="onGenderConfirm" @cancel="showGender = false" />
      </van-popup>

      <van-field label="Birth Date" readonly is-link :model-value="form.birth_date" @click="openBirthPicker" />
      <van-popup v-model:show="showBirth" position="bottom" round>
        <!-- 滚轮式年月日，手机上比日历面板好点选；默认停在 2004-01-01 -->
        <van-date-picker
          v-model="birthPickerValue"
          title="Select birth date"
          :columns-type="['year', 'month', 'day']"
          :min-date="minBirthDate"
          :max-date="maxBirthDate"
          @confirm="onBirthConfirm"
          @cancel="showBirth = false"
        />
      </van-popup>

      <van-field label="Marital Status" readonly is-link :model-value="maritalText" @click="showMarital = true" />
      <van-popup v-model:show="showMarital" position="bottom" round>
        <van-picker :columns="maritalOptions" :model-value="maritalPickerValue" @confirm="onMaritalConfirm" @cancel="showMarital = false" />
      </van-popup>
    </van-cell-group>

    <!-- B. 联系方式 -->
    <van-cell-group inset class="section" title="Contact">
      <van-field v-model="form.phone" label="Mobile" type="tel" placeholder="09XX XXX XXXX" required />
      <van-field v-model="form.phone_alt" label="Alt. number" type="tel" placeholder="Optional" />
      <van-field
        v-model="form.email"
        label="Email"
        type="email"
        maxlength="128"
        placeholder="you@example.com (optional)"
        @blur="onEmailBlur"
      />
      <van-field v-model="form.address_city" label="City" placeholder="e.g. Manila, Quezon City" />
      <van-field v-model="form.address_barangay" label="Barangay" placeholder="e.g. Barangay 123" />
    </van-cell-group>

    <!-- C. 社交账号 -->
    <van-cell-group inset class="section" title="Social Media (Optional)">
      <van-field v-model="form.fb_profile_url" label="Facebook" placeholder="https://fb.com/yourname" />
      <van-field v-model="form.tiktok_username" label="TikTok" placeholder="@yourname" />
    </van-cell-group>

    <!-- D. 证件 -->
    <van-cell-group inset class="section" title="ID Documents (Optional)">
      <van-field v-model="form.id1_type" label="ID Type" placeholder="e.g. SSS, Passport, Driver's License" />
      <van-field v-model="form.id1_number" label="ID Number" placeholder="Enter ID number" />
      <van-field label="NBI" readonly is-link :model-value="hasNbiText" @click="showNbi = true" />
      <van-popup v-model:show="showNbi" position="bottom" round>
        <van-picker :columns="nbiOptions" @confirm="onNbiConfirm" @cancel="showNbi = false" />
      </van-popup>
    </van-cell-group>

    <!-- E. 求职意向 -->
    <van-cell-group inset class="section" title="Job Preference">
      <van-field v-model="form.target_job" label="Target Job" placeholder="e.g. Driver, Cook, Housekeeper" />
      <van-field
        v-model.number="form.expected_salary"
        label="Expected pay"
        type="number"
        placeholder="e.g. 20000"
      >
        <template #extra>
          <span class="salary-unit">PHP / month</span>
        </template>
      </van-field>
      <van-field label="Available" readonly is-link :model-value="availableTimeText" @click="showAvailable = true" />
      <van-popup v-model:show="showAvailable" position="bottom" round>
        <van-picker :columns="availableOptions" @confirm="onAvailableConfirm" @cancel="showAvailable = false" />
      </van-popup>
    </van-cell-group>

    <!-- F. 技能与经验 -->
    <van-cell-group inset class="section" title="Skills & Experience">
      <van-field v-model="form.education" label="Education" placeholder="e.g. High School, College" />
      <van-field v-model="form.last_job" label="Last Job" placeholder="e.g. Jollibee | Driver | 2020-Present" />
      <van-field
        v-model="form.work_experience"
        label="Experience"
        type="textarea"
        rows="5"
        placeholder="Write one job per line, like this:
2020-2023 | Driver | Jollibee
2018-2020 | Warehouse | Puregold"
      />
    </van-cell-group>

    <!-- G. 照片与视频 -->
    <van-cell-group inset class="section" title="Photo & Video">
      <!-- 拍照 -->
      <van-field label="Your Photo">
        <template #input>
          <div class="media-upload">
            <!-- 不写 capture：让手机弹出「拍照 / 相册」选择，代录时可拍对面的人或挑现成照片 -->
            <input ref="photoInput" type="file" accept="image/*" style="display:none" @change="onPhotoTaken">
            <van-button size="small" icon="photograph" @click="photoInput?.click()">
              {{ photoPreview ? 'Retake' : 'Take Photo' }}
            </van-button>
            <img v-if="photoPreview" :src="photoPreview" class="preview-img" alt="photo">
          </div>
        </template>
      </van-field>

      <!-- 录像 -->
      <van-field label="Video ≤40s">
        <template #input>
          <div class="media-upload">
            <input ref="videoInput" type="file" accept="video/*" style="display:none" @change="onVideoTaken">
            <van-button size="small" icon="video" @click="videoInput?.click()">
              {{ videoName ? 'Retake' : 'Record Video' }}
            </van-button>

            <!-- 上传前压缩确认：必须由真实点击触发，iOS 才能激活音频上下文 -->
            <div v-if="videoPending" class="video-plan">
              <p class="video-plan-text">
                {{ videoPlanText }}
              </p>
              <div class="video-plan-actions">
                <van-button size="small" type="primary" :loading="compressing" :disabled="compressing" @click="startCompress">
                  {{ compressing ? 'Compressing…' : 'Compress' }}
                </van-button>
                <van-button size="small" :disabled="compressing" @click="useOriginalVideo">Use original</van-button>
                <van-button v-if="compressing" size="small" plain @click="cancelCompress">Cancel</van-button>
              </div>
              <van-progress v-if="compressing" :percentage="compressPercent" :show-pivot="false" />
              <p v-if="compressing" class="video-plan-text">{{ compressRemaining }}s left</p>
            </div>

            <div v-if="videoName" class="video-preview">
              <video :src="videoPreview" controls class="preview-video"></video>
              <span class="video-name">{{ videoName }} · {{ videoSizeText }}</span>
            </div>
          </div>
        </template>
      </van-field>
    </van-cell-group>

    <!-- H. 自由备注 + 简历附件 -->
    <van-cell-group inset class="section" title="Additional Info">
      <van-field
        v-model="form.applicant_remark"
        label="Anything else?"
        type="textarea"
        rows="4"
        placeholder="Tell us anything else that helps your application..."
      />
      <van-field label="Resume file">
        <template #input>
          <div class="resume-upload">
            <input
              ref="resumeInput"
              type="file"
              accept=".pdf,.doc,.docx,.xls,.xlsx,image/jpeg,image/png,image/webp,image/heic"
              style="display:none"
              @change="onResumePicked"
            >
            <div class="resume-line">
              <van-button v-if="!resumeName" size="small" icon="description" @click="resumeInput?.click()">
                Upload File
              </van-button>
              <template v-else>
                <span class="resume-name">{{ resumeName }}</span>
                <a class="resume-remove" @click.prevent="onResumeRemove">Remove</a>
              </template>
            </div>
            <p class="resume-hint">Optional — PDF, Word, Excel, or a photo of your resume.</p>
          </div>
        </template>
      </van-field>
    </van-cell-group>

    <!-- 提交按钮 -->
    <div class="submit-area">
      <p class="required-note">Fields marked * are required.</p>
      <van-button
        type="primary"
        size="large"
        block
        :loading="submitting"
        :disabled="compressing || !!videoPending"
        @click="onSubmit"
      >
        {{ uploading ? 'Uploading files...' : (submitting ? 'Submitting...' : 'Submit application') }}
      </van-button>
      <p v-if="!form.privacy_agreed" class="privacy-hint">Please agree to the privacy policy first</p>
    </div>

    <!-- 员工会话过期：就地重登，不离开当前页，已填表单与已拍媒体都不丢 -->
    <van-popup v-model:show="showRelogin" position="bottom" round :close-on-click-overlay="false">
      <div class="relogin-panel">
        <h3>Staff session expired</h3>
        <p class="relogin-tip">
          Your login has expired. Sign in again to keep this application credited to you.
          Everything you have filled in and captured stays on this page.
        </p>
        <van-cell-group inset>
          <van-field v-model="relogin.username" label="Username" placeholder="Your staff account" autocomplete="username" />
          <van-field
            v-model="relogin.password"
            type="password"
            label="Password"
            placeholder="Your password"
            autocomplete="current-password"
            @keyup.enter="onRelogin"
          />
        </van-cell-group>
        <van-button
          type="primary"
          block
          round
          class="relogin-btn"
          :loading="relogin.loading"
          :disabled="!relogin.username || !relogin.password"
          @click="onRelogin"
        >
          {{ relogin.loading ? 'Signing in...' : 'Sign In & Resubmit' }}
        </van-button>
        <p class="relogin-cancel"><a @click.prevent="cancelRelogin">Continue as applicant instead</a></p>
      </div>
    </van-popup>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showToast, showSuccessToast, showFailToast } from 'vant'
import axios from 'axios'
import { authHeaders, clearLogin, getStaff, isLoggedIn, saveLogin } from '../auth'
import { uploadMedia } from '../upload'
import {
  MAX_VIDEO_BYTES,
  MAX_VIDEO_SECONDS,
  compressVideo,
  formatSize,
  planCompression,
  probeVideo,
  supportsVideoCompression,
} from '../videoCompress'

const route = useRoute()
const router = useRouter()

// 员工代录模式：带 JWT 提交时，后端自动把来源记为该员工
const isStaff = ref(isLoggedIn())
const staff = ref(getStaff())
// 推广码：来自 URL ?ref=，仅接受后端允许的字符集
const sourceRef = ref('')

onMounted(() => {
  // 推广码存进 sessionStorage：中途刷新或跳转再回来也不会丢单
  const refCode = route.query.ref
  if (typeof refCode === 'string' && /^[A-Za-z0-9_-]{1,64}$/.test(refCode)) {
    sourceRef.value = refCode
    sessionStorage.setItem('hr_ref', refCode)
  } else {
    const saved = sessionStorage.getItem('hr_ref')
    if (saved && /^[A-Za-z0-9_-]{1,64}$/.test(saved)) sourceRef.value = saved
  }
})

function goStaffLogin() {
  router.push({ path: '/staff/login', query: { redirect: route.fullPath } })
}

function onLogout() {
  clearLogin()
  isStaff.value = false
  staff.value = null
  showToast('Signed out')
}

// 会话过期后就地重登（不跳页，已填表单与媒体都不丢）
const showRelogin = ref(false)
const relogin = reactive({ username: '', password: '', loading: false })
// 重登成功再提交若仍是 401，不再重复弹窗，避免死循环
let reloginRetried = false

async function onRelogin() {
  if (!relogin.username || !relogin.password) return
  relogin.loading = true
  try {
    const res = await axios.post('/api/auth/login', {
      username: relogin.username.trim(),
      password: relogin.password,
    })
    saveLogin(res.data.data.token, res.data.data.staff)
    isStaff.value = true
    staff.value = res.data.data.staff
    relogin.password = ''
    showRelogin.value = false
    showSuccessToast('Signed in, resubmitting...')
    reloginRetried = true
    await onSubmit()
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
    relogin.loading = false
  }
}

function cancelRelogin() {
  showRelogin.value = false
  showToast('Signed out. Tap Submit again to send this as an applicant.')
}

// 表单数据（字段对齐后端 ApplicantSubmit）
const form = reactive({
  privacy_agreed: false,
  first_name: '',
  middle_name: '',
  last_name: '',
  gender: '',
  birth_date: '',
  marital_status: null,
  phone: '',
  phone_alt: '',
  email: '',
  address_city: '',
  address_barangay: '',
  fb_profile_url: '',
  tiktok_username: '',
  id1_type: '',
  id1_number: '',
  has_nbi: null,
  target_job: '',
  expected_salary: null,
  available_time: '',
  education: '',
  last_job: '',
  work_experience: '',
  applicant_remark: '',
})

// 选择器状态
const showGender = ref(false)
const showBirth = ref(false)
const showNbi = ref(false)
const showMarital = ref(false)
const showAvailable = ref(false)

// 出生日期：滚轮默认停在 2004-01-01（打工人的常见年龄段），不是打开就停在今天
const DEFAULT_BIRTH = ['2004', '01', '01']
const birthPickerValue = ref([...DEFAULT_BIRTH])
const minBirthDate = new Date(1970, 0, 1)
// 只允许 18 岁以上：上限取 18 年前的今天
const maxBirthDate = new Date()
maxBirthDate.setFullYear(maxBirthDate.getFullYear() - 18)

// 选项（Vant 4 的 Picker 只接受 { text, value } 对象数组，传字符串会报错导致弹层空白）
const genderOptions = [
  { text: 'Male', value: 'male' },
  { text: 'Female', value: 'female' },
  // 选填项：提供置空项，选中后按空值提交（入库为 NULL）
  { text: 'Prefer not to say', value: '' },
]
const nbiOptions = [
  { text: 'Yes, I have NBI clearance', value: 'yes' },
  { text: 'No, I don\'t have', value: 'no' },
]
const maritalOptions = [
  { text: 'Single', value: 'single' },
  { text: 'Married', value: 'married' },
  { text: 'Widowed', value: 'widowed' },
  { text: 'Separated', value: 'separated' },
  { text: 'Annulled', value: 'annulled' },
  // 选填项：提供置空项，选中后按空值提交（入库为 NULL）
  { text: 'Prefer not to say', value: '' },
]
const availableOptions = [
  { text: 'Anytime', value: 'anytime' },
  { text: 'In 2 weeks', value: '2weeks' },
  { text: 'In 1 month', value: '1month' },
]

// 显示文本
const genderText = computed(() => {
  if (form.gender === 'male') return 'Male'
  if (form.gender === 'female') return 'Female'
  return ''
})
const genderPickerValue = computed(() => {
  const idx = genderOptions.findIndex(o => o.value === form.gender)
  return [genderOptions[idx >= 0 ? idx : 0].value]
})
const hasNbiText = computed(() => form.has_nbi === true ? 'Yes' : form.has_nbi === false ? 'No' : 'Select')
const availableTimeText = computed(() => {
  const map = { anytime: 'Anytime', '2weeks': 'In 2 weeks', '1month': 'In 1 month' }
  return map[form.available_time] || 'Select'
})
// 显示文本：直接从 options 反查，以后加选项只需改 maritalOptions 一处
const maritalText = computed(() => {
  if (form.marital_status === null) return 'Select'
  return maritalOptions.find(o => o.value === form.marital_status)?.text || 'Select'
})
// 再次打开滚轮时回显已选项，避免清空后直接点确认又被改回第一项
const maritalPickerValue = computed(() => {
  const idx = maritalOptions.findIndex(o => o.value === form.marital_status)
  return [maritalOptions[idx >= 0 ? idx : 0].value]
})

// 回调
function onGenderConfirm({ selectedValues }) {
  form.gender = selectedValues[0]
  showGender.value = false
}
function openBirthPicker() {
  // 已选过就回显，没选过就停在默认的 2004-01-01
  birthPickerValue.value = form.birth_date ? form.birth_date.split('-') : [...DEFAULT_BIRTH]
  showBirth.value = true
}
function onBirthConfirm({ selectedValues }) {
  // 手动补零拼接，不能用 toISOString()（UTC 会让东八区的生日少一天）
  const pad = (n) => String(n).padStart(2, '0')
  form.birth_date = `${selectedValues[0]}-${pad(selectedValues[1])}-${pad(selectedValues[2])}`
  showBirth.value = false
}
function onNbiConfirm({ selectedValues }) {
  form.has_nbi = selectedValues[0] === 'yes'
  showNbi.value = false
}
function onMaritalConfirm({ selectedValues }) {
  form.marital_status = selectedValues[0]
  showMarital.value = false
}
function onAvailableConfirm({ selectedOptions }) {
  form.available_time = selectedOptions[0]?.value || ''
  showAvailable.value = false
}

// 媒体
const photoInput = ref(null)
const videoInput = ref(null)
const photoPreview = ref('')
const videoPreview = ref('')
const videoName = ref('')
let photoFile = null
let videoFile = null
// 已上传成功的对象 key：会话过期重登后重提时复用，避免同一份媒体传两遍
let photoKey = null
let videoKey = null
// 本次投递共用的 OSS 上传会话（照片/视频同前缀，提交时回传 token）
let uploadSession = null

// 简历附件：只允许一个文件，PDF / Word / Excel / 图片都能收
const resumeInput = ref(null)
const resumeName = ref('')
let resumeFile = null
let resumeKey = null

const RESUME_EXTS = ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'jpg', 'jpeg', 'png', 'webp', 'heic']
const RESUME_MAX_BYTES = 100 * 1024 * 1024

function onResumePicked(e) {
  const file = e.target.files?.[0]
  // 清空 input，保证再选同一个文件也能触发 change
  e.target.value = ''
  if (!file) return
  const ext = (file.name.split('.').pop() || '').toLowerCase()
  if (!RESUME_EXTS.includes(ext)) {
    showFailToast('Please choose a PDF, Word, Excel, or image file')
    return
  }
  if (file.size > RESUME_MAX_BYTES) {
    showFailToast('File is too large (max 100MB)')
    return
  }
  resumeFile = file
  resumeName.value = file.name
  resumeKey = null
}

function onResumeRemove() {
  resumeFile = null
  resumeKey = null
  resumeName.value = ''
}

// 手机原图 6~12MB，楼道里传一张要十几秒：长边压到 1280 的 JPEG，体积降到几百 KB
const MAX_PHOTO_EDGE = 1280
const PHOTO_QUALITY = 0.85

async function compressPhoto(file) {
  // 小图没必要压；HEIC/HEIF 多数浏览器解不了，直接走原图
  if (file.size <= 1024 * 1024 || /hei[cf]/i.test(file.type || '')) return file
  try {
    const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
    const scale = Math.min(1, MAX_PHOTO_EDGE / Math.max(bitmap.width, bitmap.height))
    if (scale === 1) {
      bitmap.close?.()
      return file
    }
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(bitmap.width * scale)
    canvas.height = Math.round(bitmap.height * scale)
    canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height)
    bitmap.close?.()
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', PHOTO_QUALITY))
    if (!blob || blob.size >= file.size) return file
    const name = (file.name || 'photo').replace(/\.[^.]+$/, '') + '.jpg'
    return new File([blob], name, { type: 'image/jpeg' })
  } catch {
    // 解不出（老 WebView / 特殊编码）就退回原图，不阻塞提交
    return file
  }
}

async function onPhotoTaken(e) {
  const file = e.target.files?.[0]
  if (!file) return
  // 释放上一次预览，否则重拍会一直泄漏 blob
  if (photoPreview.value) URL.revokeObjectURL(photoPreview.value)
  photoFile = await compressPhoto(file)
  photoKey = null
  photoPreview.value = URL.createObjectURL(photoFile)
  // 清空 input，保证再选同一张照片也能触发 change
  e.target.value = ''
}

// 视频压缩状态
const videoPending = ref(null)   // { file, meta, plan }
const compressing = ref(false)
const compressPercent = ref(0)
const compressRemaining = ref(0)
const videoSizeText = ref('')
let compressStatus = null

const videoPlanText = computed(() => {
  const p = videoPending.value
  if (!p) return ''
  const { file, meta, plan } = p
  const src = `${Math.round(meta.duration || 0)}s · ${meta.width}×${meta.height} · ${formatSize(file.size)}`
  return `${src} → about ${formatSize(plan.estBytes)} after compression`
})

function resetVideo() {
  videoFile = null
  videoKey = null
  videoName.value = ''
  videoSizeText.value = ''
  videoPending.value = null
  compressing.value = false
  compressPercent.value = 0
  compressStatus = null
  if (videoPreview.value) {
    URL.revokeObjectURL(videoPreview.value)
    videoPreview.value = ''
  }
  if (videoInput.value) videoInput.value.value = ''
}

function acceptVideo(file) {
  videoFile = file
  videoKey = null
  videoName.value = file.name || 'video'
  videoSizeText.value = formatSize(file.size)
  videoPreview.value = URL.createObjectURL(file)
}

async function onVideoTaken(e) {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file) return
  resetVideo()

  if (file.size > MAX_VIDEO_BYTES) {
    showFailToast(`Video is too large. Please keep it under ${formatSize(MAX_VIDEO_BYTES)}.`)
    return
  }

  // 文件大小与时长没有稳定关系，6 秒的 4K 也可能很大，先读真实时长
  let meta = null
  try {
    meta = await probeVideo(file)
  } catch {
    meta = null
  }

  if (meta && Number.isFinite(meta.duration) && meta.duration > MAX_VIDEO_SECONDS + 1) {
    showFailToast(`Video is ${Math.round(meta.duration)}s, please keep it within ${MAX_VIDEO_SECONDS}s`)
    return
  }

  // 小文件直接放行；浏览器不支持压缩也直接放行，绝不阻塞提交
  const plan = meta ? planCompression(file, meta) : { action: 'skip', reason: 'unknown' }
  if (plan.action !== 'compress' || !meta || !supportsVideoCompression()) {
    acceptVideo(file)
    return
  }

  videoPending.value = { file, meta, plan }
}

async function startCompress() {
  const pending = videoPending.value
  if (!pending || compressing.value) return

  compressing.value = true
  compressPercent.value = 0
  compressRemaining.value = Math.ceil(pending.meta.duration || 0)
  const status = { cancelled: false }
  compressStatus = status

  try {
    const out = await compressVideo(pending.file, pending.meta, {
      status,
      onProgress: ({ percent, remaining }) => {
        compressPercent.value = percent
        compressRemaining.value = remaining
      },
    })
    videoPending.value = null
    if (out.file.size >= pending.file.size) {
      acceptVideo(pending.file)
      showToast('Already small enough, using original')
    } else {
      acceptVideo(out.file)
      showSuccessToast(`Compressed to ${formatSize(out.file.size)}`)
    }
  } catch (err) {
    const code = err?.message || ''
    if (code === 'CANCELLED') {
      // 保留待选项，让用户重新选择「压缩」或「原片」
      showToast('Compression cancelled')
    } else {
      videoPending.value = null
      acceptVideo(pending.file)
      showFailToast(`Compression failed (${code || 'error'}). Using original video.`)
    }
  } finally {
    compressing.value = false
    compressStatus = null
    compressPercent.value = 0
  }
}

function cancelCompress() {
  if (compressStatus) compressStatus.cancelled = true
}

function useOriginalVideo() {
  const pending = videoPending.value
  if (!pending) return
  videoPending.value = null
  acceptVideo(pending.file)
}

// v-model.number 清空后会变成 ""，误输负号或小数又会被后端 int + ge=0 拒掉
function normalizeSalary(value) {
  const n = Number(value)
  return Number.isFinite(n) && n > 0 ? Math.round(n) : null
}

// 提交
const submitting = ref(false)
const uploading = ref(false)

onBeforeUnmount(() => {
  if (photoPreview.value) URL.revokeObjectURL(photoPreview.value)
  if (videoPreview.value) URL.revokeObjectURL(videoPreview.value)
  // 离开页面时终止还在进行的压缩，避免后台空跑耗电
  if (compressStatus) compressStatus.cancelled = true
})

// Email 只做格式初筛（不验证邮箱是否真实存在），选填
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

function onEmailBlur() {
  form.email = form.email.trim()
  if (form.email && !EMAIL_PATTERN.test(form.email)) {
    showFailToast('Please enter a valid email address')
  }
}

// 仅 First Name / Last Name / Mobile Number 必填，其余全部选填
function missingRequiredFields() {
  const checks = [
    ['First Name', form.first_name.trim()],
    ['Last Name', form.last_name.trim()],
    ['Mobile Number', form.phone.trim()],
  ]
  return checks.filter(([, filled]) => !filled).map(([label]) => label)
}

async function onSubmit() {
  if (!form.privacy_agreed) {
    showFailToast('Please agree to the privacy policy')
    return
  }
  if (form.email && !EMAIL_PATTERN.test(form.email.trim())) {
    showFailToast('Please enter a valid email address')
    return
  }
  const missing = missingRequiredFields()
  if (missing.length) {
    showFailToast(`Please fill in: ${missing.join(', ')}`)
    return
  }
  submitting.value = true

  try {
    // 0. 先预检手机号，避免照片视频都传完才发现号码重复
    const check = await axios.post(
      '/api/applicant/check-phone',
      { phone: form.phone },
      { headers: authHeaders() },
    )
    if (check.data?.data?.exists) {
      showFailToast('This mobile number has already applied. Please contact us to update your record.')
      return
    }

    // 1. 先上传照片、视频与简历附件（已传过的复用 key，重登重提不会重复上传）
    if ((photoFile && !photoKey) || (videoFile && !videoKey) || (resumeFile && !resumeKey)) {
      uploading.value = true
      try {
        if (photoFile && !photoKey) {
          const uploaded = await uploadMedia(photoFile, { session: uploadSession })
          photoKey = uploaded.key
          uploadSession = uploaded.session || uploadSession
        }
        if (videoFile && !videoKey) {
          const uploaded = await uploadMedia(videoFile, { session: uploadSession })
          videoKey = uploaded.key
          uploadSession = uploaded.session || uploadSession
        }
        if (resumeFile && !resumeKey) {
          resumeKey = (await uploadMedia(resumeFile, { privateUpload: true })).key
        }
      } finally {
        uploading.value = false
      }
    }

    // 2. 提交表单数据
    const payload = {
      privacy_agreed: form.privacy_agreed,
      first_name: form.first_name,
      middle_name: form.middle_name || null,
      last_name: form.last_name,
      gender: form.gender || null,
      birth_date: form.birth_date || null,
      marital_status: form.marital_status || null,
      phone: form.phone,
      phone_alt: form.phone_alt || null,
      email: form.email.trim() || null,
      address_city: form.address_city || null,
      address_barangay: form.address_barangay || null,
      fb_profile_url: form.fb_profile_url || null,
      tiktok_username: form.tiktok_username || null,
      id1_type: form.id1_type || null,
      id1_number: form.id1_number || null,
      has_nbi: form.has_nbi,
      target_job: form.target_job || null,
      expected_salary: normalizeSalary(form.expected_salary),
      available_time: form.available_time || null,
      education: form.education || null,
      last_job: form.last_job || null,
      work_experience: form.work_experience || null,
      applicant_remark: form.applicant_remark || null,
      photo_oss_key: photoKey,
      video_oss_key: videoKey,
      resume_oss_key: resumeKey,
      resume_file_name: resumeName.value || null,
      upload_session_token: uploadSession?.session_token || null,
      source_ref: sourceRef.value || null,
    }

    const res = await axios.post('/api/applicant/submit', payload, {
      headers: authHeaders(),
    })

    if (res.data.code === 0) {
      showSuccessToast('Submitted successfully!')
      router.push('/apply/success')
    } else {
      showFailToast(res.data.message || 'Submission failed')
    }
  } catch (err) {
    console.error(err)
    const status = err.response?.status
    const detail = err.response?.data?.detail

    if (status === 401) {
      // 员工 token 过期或账号被停用：先清掉本地登录态，避免顶部继续显示「假的已登录」
      const wasStaff = isStaff.value
      clearLogin()
      isStaff.value = false
      staff.value = null
      if (wasStaff && !reloginRetried) {
        relogin.username = ''
        relogin.password = ''
        showRelogin.value = true
        showToast('Your staff session has expired, please sign in again')
      } else if (wasStaff) {
        showFailToast('Session expired again, please sign in from the top bar')
      } else {
        // 已不是员工态却仍 401：token 已清，按普通提交再试一次
        showFailToast('Your session has expired. Please tap Submit again.')
      }
      return
    } else if (status === 409) {
      showFailToast(typeof detail === 'string' ? detail : 'This phone number has already been submitted')
    } else if (err.message === 'FILE_TOO_LARGE') {
      showFailToast('File is larger than 100MB, please choose a smaller one')
    } else if (status === 429) {
      showFailToast('Too many attempts, please try again in a minute')
    } else if (status === 422 && Array.isArray(detail)) {
      // Pydantic 校验错误：取第一条的提示信息
      showFailToast(detail[0]?.msg?.replace(/^Value error,\s*/, '') || 'Please check your input')
    } else if (typeof detail === 'string') {
      // 400 等业务校验错误（手机号格式、上传类型等）
      showFailToast(detail)
    } else {
      showFailToast('Network error, please try again')
    }
  } finally {
    submitting.value = false
    uploading.value = false
  }
}
</script>

<style scoped>
.apply-page {
  padding-bottom: 2.5rem;
  max-width: 560px;
  margin: 0 auto;
}
.masthead {
  padding: 1.75rem 1.25rem 1rem;
}
.masthead-inner {
  border-bottom: 3px double var(--rule);
  padding-bottom: 1.15rem;
}
.masthead-note {
  margin: 0 0 0.3rem;
  font-size: 0.78rem;
  color: var(--ink-faint);
}
.masthead h1 {
  margin: 0 0 0.6rem;
  font-family: var(--serif);
  font-size: 2rem;
  line-height: 1.15;
  font-weight: 600;
  color: var(--teal);
}
.masthead h1 mark {
  background: linear-gradient(transparent 58%, rgba(224, 165, 38, 0.5) 58%);
  color: inherit;
  padding: 0 0.08em;
}
.lead {
  margin: 0;
  max-width: 34em;
  font-size: 0.92rem;
  line-height: 1.55;
  color: var(--ink-soft);
}
.ref-tag {
  margin: 0.6rem 0 0;
  font-size: 0.8rem;
  color: var(--teal);
}
.salary-unit {
  margin-left: 0.35rem;
  font-size: 0.78rem;
  color: var(--ink-faint);
  white-space: nowrap;
}
.staff-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.5rem;
  margin: 0.9rem 1rem 0;
  padding: 0.55rem 0.75rem;
  border-left: 3px solid var(--sun);
  background: rgba(224, 165, 38, 0.08);
  font-size: 0.8rem;
  color: var(--ink-soft);
}
.staff-bar a {
  color: var(--teal);
  font-weight: 600;
  text-decoration: underline;
  text-underline-offset: 2px;
  white-space: nowrap;
}
.section {
  margin-top: 0.25rem;
}
.consent {
  margin-top: 1rem;
}
.consent :deep(.van-cell) {
  background: #f8f1e2;
}
.consent :deep(.van-checkbox__label) {
  margin-left: 0.55rem;
}
.privacy-text {
  font-size: 0.85rem;
  line-height: 1.5;
}
.media-upload {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.resume-upload {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  align-items: flex-start;
}
.resume-line {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
}
.resume-name {
  font-size: 0.85rem;
  color: var(--ink-soft);
  word-break: break-all;
}
.resume-remove {
  font-size: 0.8rem;
  color: var(--teal);
  text-decoration: underline;
  text-underline-offset: 2px;
  white-space: nowrap;
}
.resume-hint {
  margin: 0;
  font-size: 0.75rem;
  line-height: 1.5;
  color: var(--ink-faint);
}
.preview-img {
  max-width: 200px;
  border-radius: 6px;
  border: 1px solid var(--rule);
}
.preview-video {
  max-width: 100%;
  max-height: 200px;
  border-radius: 6px;
}
.video-name {
  font-size: 0.85rem;
  color: var(--ink-soft);
}
.video-plan {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.625rem 0.75rem;
  background: #f6efe0;
  border: 1px solid var(--rule);
  border-radius: 8px;
}
.video-plan-text {
  margin: 0;
  font-size: 0.8rem;
  color: var(--ink-soft);
  line-height: 1.4;
}
.video-plan-actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.submit-area {
  padding: 1.5rem 1rem 2rem;
}
.required-note {
  margin: 0 0 0.7rem;
  text-align: center;
  font-size: 0.78rem;
  color: var(--ink-faint);
}
.privacy-hint {
  text-align: center;
  color: var(--danger);
  font-size: 0.85rem;
  margin-top: 0.75rem;
}
.relogin-panel {
  padding: 1.25rem 0 1.5rem;
}
.relogin-panel h3 {
  margin: 0 1rem 0.5rem;
  font-size: 1.05rem;
}
.relogin-tip {
  margin: 0 1rem 1rem;
  font-size: 0.85rem;
  line-height: 1.5;
  color: var(--ink-soft);
}
.relogin-btn {
  margin: 1rem 1rem 0;
  width: calc(100% - 2rem);
}
.relogin-cancel {
  text-align: center;
  font-size: 0.85rem;
  margin: 1rem 0 0;
}
.relogin-cancel a {
  color: var(--ink-faint);
}
</style>
