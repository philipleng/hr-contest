import { onBeforeUnmount, onMounted, ref } from 'vue'

// 与 CSS 断点保持一致：<= 900px 视为移动端（侧边栏收起、表格换卡片）
export function useIsMobile(breakpoint = 900) {
  const isMobile = ref(typeof window !== 'undefined' ? window.innerWidth <= breakpoint : false)
  let query = null

  const update = (event) => {
    isMobile.value = event.matches
  }

  onMounted(() => {
    query = window.matchMedia(`(max-width: ${breakpoint}px)`)
    isMobile.value = query.matches
    query.addEventListener('change', update)
  })

  onBeforeUnmount(() => {
    query?.removeEventListener('change', update)
  })

  return isMobile
}
