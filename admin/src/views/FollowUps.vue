<template>
  <AdminLayout active="follow-ups">
    <div class="page-head">
      <div>
        <h2>Follow-ups</h2>
        <p>Contacts due today, including overdue follow-ups.</p>
      </div>
    </div>

    <el-card class="table-card">
      <el-table :data="items" v-loading="loading" empty-text="Nothing due today.">
        <el-table-column label="Applicant" min-width="160">
          <template #default="{ row }">
            <div class="cell-name">{{ row.applicant_name }}</div>
            <div class="cell-sub">#{{ row.applicant_id }} · {{ row.phone }}</div>
          </template>
        </el-table-column>
        <el-table-column label="Last Result" min-width="130">
          <template #default="{ row }">
            {{ channelLabel(row.channel) }} · {{ resultLabel(row.result) }}
          </template>
        </el-table-column>
        <el-table-column prop="note" label="Note" min-width="180" show-overflow-tooltip />
        <el-table-column label="Next Follow-up" width="170">
          <template #default="{ row }">
            <span :class="{ 'is-overdue': isOverdue(row.next_follow_at) }">
              {{ formatTime(row.next_follow_at) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="operator_name" label="Operator" width="120" />
        <el-table-column label="" width="90" align="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openApplicant(row)">Open</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </AdminLayout>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AdminLayout from '../components/AdminLayout.vue'
import http from '../api/http'

const router = useRouter()
const loading = ref(false)
const items = ref([])

const channelMap = {
  phone: 'Phone',
  sms: 'SMS',
  whatsapp: 'WhatsApp',
  messenger: 'Messenger',
  email: 'Email',
  inperson: 'In person',
}
const resultMap = {
  reached: 'Reached',
  no_answer: 'No answer',
  wrong_number: 'Wrong number',
  refused: 'Refused',
  interview_booked: 'Interview booked',
}

function channelLabel(value) { return channelMap[value] || value }
function resultLabel(value) { return resultMap[value] || value }

function formatTime(value) {
  return value ? String(value).replace('T', ' ').slice(0, 16) : ''
}

function isOverdue(value) {
  return value ? new Date(value).getTime() < Date.now() : false
}

async function fetchFollowUps() {
  loading.value = true
  try {
    const res = await http.get('/contact/follow-ups')
    items.value = res.data || []
  } finally {
    loading.value = false
  }
}

function openApplicant(row) {
  // 回到列表并按手机号搜索，避免再做一个详情页
  router.push({ path: '/applicant', query: { keyword: row.phone } })
}

onMounted(fetchFollowUps)
</script>

<style scoped>
.page-head { margin-bottom: 14px; }
.page-head h2 { margin: 0; font-size: 20px; color: var(--ap-ink); }
.page-head p { margin: 4px 0 0; font-size: 12px; color: var(--ap-muted); }
.table-card :deep(.el-card__body) { padding: 0; }
.cell-name { font-weight: 600; color: var(--ap-ink); }
.cell-sub { font-family: var(--ap-mono); font-size: 10.5px; color: var(--ap-muted); margin-top: 2px; }
.is-overdue { color: var(--ap-red); font-weight: 600; }
</style>
