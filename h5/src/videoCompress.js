/**
 * 设备端视频压缩（纯浏览器 API，无第三方依赖）
 *
 * 背景：菲律宾移动网络差、申请人流量包小，而手机相机 40 秒 1080p 原片可达 60~100MB。
 * 方案：上传之前用 canvas + MediaRecorder 实时重编码到 1080p / 4Mbps，
 * 40 秒视频压到约 20MB，省申请人的流量与上传时间。
 *
 * 原则：尽力压缩、失败不阻塞。任何一步出错都抛错，由调用方回退原片。
 */

export const MAX_VIDEO_SECONDS = 40
export const MAX_VIDEO_BYTES = 100 * 1024 * 1024

// 已经足够小的文件不再压缩：多等一次实时编码不划算
const SKIP_BYTES = 8 * 1024 * 1024

// 1080p 是业务选定的清晰度下限；比它小的源不放大
const TARGET_SHORT_SIDE = 1080

function bitrateFor(shortSide) {
  if (shortSide >= 1000) return 4_000_000
  if (shortSide >= 700) return 2_500_000
  return 1_500_000
}

export function formatSize(bytes) {
  if (!bytes) return '0 MB'
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export function supportsVideoCompression() {
  return typeof window !== 'undefined'
    && typeof window.MediaRecorder !== 'undefined'
    && typeof HTMLCanvasElement.prototype.captureStream === 'function'
    && typeof (window.AudioContext || window.webkitAudioContext) === 'function'
}

/** 读取视频元数据；读不出时抛错，由调用方降级 */
export function probeVideo(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const video = document.createElement('video')
    video.preload = 'metadata'
    video.muted = true
    video.onloadedmetadata = () => {
      const meta = {
        duration: video.duration,
        width: video.videoWidth,
        height: video.videoHeight,
      }
      URL.revokeObjectURL(url)
      resolve(meta)
    }
    video.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('PROBE_FAILED'))
    }
    video.src = url
  })
}

/** 决定压不压：{ action: 'compress' | 'skip' } */
export function planCompression(file, meta) {
  const shortSide = Math.min(meta.width || 0, meta.height || 0)
  if (!shortSide) return { action: 'skip', reason: 'unknown' }
  if (file.size <= SKIP_BYTES && shortSide <= TARGET_SHORT_SIDE) {
    return { action: 'skip', reason: 'small' }
  }

  const outShort = Math.min(TARGET_SHORT_SIDE, shortSide)
  const scale = outShort / shortSide
  const width = even(meta.width * scale)
  const height = even(meta.height * scale)
  const bitrate = bitrateFor(outShort)
  const duration = Number.isFinite(meta.duration) ? meta.duration : 40
  const estBytes = Math.round(((bitrate + 96_000) * duration) / 8)

  return { action: 'compress', width, height, bitrate, estBytes }
}

function even(n) {
  const v = Math.round(n)
  return v % 2 === 0 ? v : v - 1
}

function pickMimeType() {
  const candidates = [
    'video/mp4;codecs=avc1.42E01E,mp4a.40.2',
    'video/mp4',
    'video/webm;codecs=vp8,opus',
    'video/webm',
  ]
  return candidates.find((t) => window.MediaRecorder.isTypeSupported(t)) || ''
}

/**
 * 压缩视频。必须在用户点击的调用栈里触发（iOS 要求 AudioContext 在手势内 resume）。
 *
 * @param {File} file
 * @param {{duration:number,width:number,height:number}} meta
 * @param {{status?:{cancelled:boolean}, onProgress?:(p:{percent:number,remaining:number})=>void}} options
 * @returns {Promise<{file: File, width: number, height: number}>}
 */
export async function compressVideo(file, meta, options = {}) {
  if (!supportsVideoCompression()) throw new Error('UNSUPPORTED')

  const { status = { cancelled: false }, onProgress } = options
  const plan = planCompression(file, meta)
  const mimeType = pickMimeType()
  if (!mimeType) throw new Error('UNSUPPORTED')

  const url = URL.createObjectURL(file)
  const video = document.createElement('video')
  video.src = url
  video.playsInline = true
  video.preload = 'auto'

  let audioCtx = null
  let recorder = null
  let wakeLock = null
  let rafId = null
  let watchdog = null
  let timeoutId = null
  let hiddenSince = null
  let finished = false

  let rejectAbort = () => {}
  const aborted = new Promise((_, reject) => { rejectAbort = reject })

  const cleanup = () => {
    if (rafId) cancelAnimationFrame(rafId)
    if (watchdog) clearTimeout(watchdog)
    if (timeoutId) clearTimeout(timeoutId)
    document.removeEventListener('visibilitychange', onVisibility)
    try {
      if (recorder && recorder.state !== 'inactive') recorder.stop()
    } catch { /* ignore */ }
    try { video.pause() } catch { /* ignore */ }
    video.removeAttribute('src')
    video.load()
    URL.revokeObjectURL(url)
    if (audioCtx) audioCtx.close().catch(() => {})
    wakeLock?.release?.().catch(() => {})
  }

  const abort = (code) => {
    if (finished) return
    finished = true
    cleanup()
    rejectAbort(new Error(code))
  }

  // 切后台暂停而不是丢弃，回来继续；离开超过 60 秒才放弃
  const onVisibility = () => {
    if (document.hidden) {
      hiddenSince = Date.now()
      try { video.pause() } catch { /* ignore */ }
      try { recorder?.pause() } catch { /* ignore */ }
    } else {
      if (hiddenSince && Date.now() - hiddenSince > 60_000) {
        abort('CANCELLED')
        return
      }
      hiddenSince = null
      try { recorder?.resume() } catch { /* ignore */ }
      video.play().catch(() => {})
    }
  }

  try {
    // 握手：音频上下文尽量早 resume，保留用户手势的有效期
    const AudioCtor = window.AudioContext || window.webkitAudioContext
    audioCtx = new AudioCtor()
    const resumePromise = audioCtx.resume()

    await waitFor(video, 'loadedmetadata', 10_000)

    const canvas = document.createElement('canvas')
    canvas.width = plan.width
    canvas.height = plan.height
    const ctx = canvas.getContext('2d', { alpha: false })

    const stream = canvas.captureStream(30)

    await resumePromise
    const source = audioCtx.createMediaElementSource(video)
    const dest = audioCtx.createMediaStreamDestination()
    source.connect(dest)
    const audioTracks = dest.stream.getAudioTracks()
    if (!audioTracks.length) throw new Error('NO_AUDIO')
    audioTracks.forEach((t) => stream.addTrack(t))

    const chunks = []
    recorder = new MediaRecorder(stream, {
      mimeType,
      videoBitsPerSecond: plan.bitrate,
      audioBitsPerSecond: 96_000,
    })
    recorder.ondataavailable = (e) => {
      if (e.data && e.data.size) chunks.push(e.data)
    }
    const stopped = new Promise((resolve) => { recorder.onstop = resolve })
    recorder.start(1000)

    if (navigator.wakeLock?.request) {
      wakeLock = await navigator.wakeLock.request('screen').catch(() => null)
    }

    document.addEventListener('visibilitychange', onVisibility)

    const duration = Number.isFinite(meta.duration) && meta.duration > 0 ? meta.duration : 40
    watchdog = setTimeout(() => abort('TIMEOUT'), duration * 1000 + 8_000)

    await video.play()

    const draw = () => {
      if (status.cancelled) {
        abort('CANCELLED')
        return
      }
      if (video.ended || video.currentTime >= duration - 0.05) {
        try {
          if (recorder.state !== 'inactive') recorder.stop()
        } catch { /* ignore */ }
        return
      }
      try {
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
      } catch {
        abort('FAILED')
        return
      }
      onProgress?.({
        percent: Math.min(99, Math.round((video.currentTime / duration) * 100)),
        remaining: Math.max(0, Math.ceil(duration - video.currentTime)),
      })
      rafId = requestAnimationFrame(draw)
    }
    rafId = requestAnimationFrame(draw)

    timeoutId = setTimeout(() => abort('TIMEOUT'), duration * 1000 + 10_000)

    await Promise.race([stopped, aborted])

    if (status.cancelled || !chunks.length) {
      throw new Error('CANCELLED')
    }

    const type = mimeType.split(';')[0]
    const blob = new Blob(chunks, { type })
    const ext = type === 'video/mp4' ? '.mp4' : '.webm'
    const base = (file.name || 'video').replace(/\.[^.]+$/, '')

    if (!finished) {
      finished = true
      cleanup()
    }

    return {
      file: new File([blob], `${base}${ext}`, { type }),
      width: canvas.width,
      height: canvas.height,
    }
  } catch (err) {
    if (!finished) {
      finished = true
      cleanup()
    }
    if (err instanceof Error && ['CANCELLED', 'UNSUPPORTED', 'NO_AUDIO', 'TIMEOUT'].includes(err.message)) {
      throw err
    }
    throw new Error('FAILED')
  }
}

function waitFor(target, event, timeout) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('TIMEOUT')), timeout)
    target.addEventListener(event, () => {
      clearTimeout(timer)
      resolve()
    }, { once: true })
  })
}
