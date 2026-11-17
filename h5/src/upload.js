// 媒体上传：优先 OSS STS 直传，后端未配置 OSS 时退回本地上传
import axios from 'axios'
import { authHeaders } from './auth'

const MAX_BYTES = 100 * 1024 * 1024
const PART_SIZE = 1024 * 1024
const MAX_RETRY = 3

const MIME_EXT = {
  'image/jpeg': '.jpg',
  'image/png': '.png',
  'image/webp': '.webp',
  'image/heic': '.heic',
  'image/heif': '.heic',
  'video/mp4': '.mp4',
  'video/quicktime': '.mov',
  'application/pdf': '.pdf',
  'application/msword': '.doc',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
  'application/vnd.ms-excel': '.xls',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
}

function extOf(file) {
  const name = file.name || ''
  const dot = name.lastIndexOf('.')
  if (dot > -1) return name.slice(dot).toLowerCase()
  // 手机相机可能不给扩展名，按 MIME 兜底
  return MIME_EXT[(file.type || '').toLowerCase()] || ''
}

function randomKey(prefix, ext) {
  // crypto.randomUUID 在非 HTTPS 环境不可用，回退到随机十六进制
  const rand = (typeof crypto !== 'undefined' && crypto.randomUUID)
    ? crypto.randomUUID().replace(/-/g, '')
    : Math.random().toString(16).slice(2).padEnd(8, '0')
      + Math.random().toString(16).slice(2).padEnd(8, '0')
  return `${prefix}${rand.slice(0, 16)}${ext}`
}

async function localUpload(file, kind = 'media') {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('kind', kind)
  const res = await axios.post('/api/oss/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data', ...authHeaders() },
  })
  return res.data.data.key
}

async function fetchSession() {
  try {
    const res = await axios.post('/api/oss/session', null, { headers: authHeaders() })
    return res.data?.data || null
  } catch (err) {
    // 503 = 后端没配 OSS，本地开发走本地上传兜底；其它错误照常抛出
    if (err.response?.status === 503) return null
    throw err
  }
}

// 弱网下单次 PUT 断了就得整包重来，改用分片上传并在失败时带 checkpoint 续传
async function ossUpload(client, key, file) {
  let checkpoint
  let lastError
  for (let attempt = 0; attempt < MAX_RETRY; attempt += 1) {
    try {
      await client.multipartUpload(key, file, {
        partSize: PART_SIZE,
        checkpoint,
        // 第二个参数是断点信息，下一次重试带上它就能从已成功的分片继续
        progress: (_percent, cp) => { checkpoint = cp },
      })
      return
    } catch (err) {
      lastError = err
    }
  }
  throw lastError
}

export async function uploadMedia(file, { privateUpload = false, session = null } = {}) {
  if (file.size > MAX_BYTES) {
    throw new Error('FILE_TOO_LARGE')
  }

  // 简历含 PII，固定走本地私有目录；OSS 直传对象是可公开直连的，不能用于简历
  if (privateUpload) {
    return { key: await localUpload(file, 'resume'), session: null }
  }

  // 一次投递共用一个上传会话：前缀受限、15 分钟失效
  const uploadSession = session || await fetchSession()
  if (!uploadSession) {
    return { key: await localUpload(file), session: null }
  }

  // ali-oss 体积较大（约 680KB），按需加载：没传照片/视频的求职者不会下载
  const { default: OSS } = await import('ali-oss')
  const client = new OSS({
    region: uploadSession.region,
    accessKeyId: uploadSession.access_key_id,
    accessKeySecret: uploadSession.access_key_secret,
    stsToken: uploadSession.security_token,
    bucket: uploadSession.bucket,
    ...(uploadSession.endpoint ? { endpoint: uploadSession.endpoint } : {}),
    secure: true,
  })

  const key = randomKey(uploadSession.prefix, extOf(file))
  await ossUpload(client, key, file)
  return { key, session: uploadSession }
}
