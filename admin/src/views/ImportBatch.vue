<template>
  <AdminLayout active="import">
    <div class="page-head">
      <div>
        <h2>Batch Import</h2>
        <p>Download the Excel template, upload applicant spreadsheets, and review import history.</p>
      </div>
      <div class="head-actions">
        <el-button :loading="downloadingTemplate" @click="downloadTemplate">
          <el-icon style="margin-right:4px"><Download /></el-icon>
          Download Template
        </el-button>
      </div>
    </div>

    <!-- 上传操作区 -->
    <el-card class="upload-card">
      <div class="upload-area">
        <el-upload
          ref="uploadRef"
          class="import-uploader"
          drag
          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          :auto-upload="false"
          :limit="1"
          v-model:file-list="fileList"
          :on-change="onFileChange"
          :on-remove="onFileRemove"
          :on-exceed="onFileExceed"
        >
          <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
          <div class="el-upload__text">
            Drop an <strong>.xlsx</strong> file here, or <em>click to select</em>
          </div>
          <template #tip>
            <div class="el-upload__tip">
              Only .xlsx files are supported. Use the template above to ensure columns match.
            </div>
          </template>
        </el-upload>

        <div class="upload-actions">
          <el-button
            type="primary"
            :disabled="!selectedFile"
            :loading="uploading"
            @click="submitUpload"
          >
            {{ uploading ? 'Importing...' : 'Upload & Import' }}
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- 本次导入结果反馈卡 -->
    <el-card v-if="latestResult" class="result-card">
      <div class="result-head">
        <div>
          <h3>Latest Import Result</h3>
          <p class="result-file">{{ latestResult.file_name }}</p>
        </div>
        <span class="result-time">{{ formatTime(latestResult.created_at) }}</span>
      </div>

      <div class="result-stats">
        <div class="stat">
          <span class="stat-label">Total</span>
          <span class="stat-value">{{ latestResult.total_count }}</span>
        </div>
        <div class="stat">
          <span class="stat-label">Imported</span>
          <span class="stat-value is-green">{{ latestResult.success_count }}</span>
        </div>
        <div class="stat">
          <span class="stat-label">Failed</span>
          <span class="stat-value is-red">{{ latestResult.fail_count }}</span>
        </div>
      </div>

      <template v-if="latestResult.failures?.length">
        <h4 class="failures-title">Row Errors ({{ latestResult.failures.length }})</h4>
        <el-table :data="latestResult.failures" size="small" border max-height="280">
          <el-table-column prop="row" label="Excel Row" width="110" class-name="col-mono" />
          <el-table-column prop="reason" label="Reason" min-width="240" />
        </el-table>
      </template>
    </el-card>

    <!-- 历史导入批次记录 -->
    <div class="section-head">
      <h3>Import History</h3>
    </div>

    <el-card v-if="!isMobile" class="table-card">
      <el-table :data="batches.items" v-loading="loadingBatches" empty-text="No import batches yet.">
        <el-table-column prop="id" label="ID" width="72" class-name="col-mono" />
        <el-table-column prop="file_name" label="File Name" min-width="200" show-overflow-tooltip />
        <el-table-column prop="total_count" label="Total" width="90" class-name="col-mono" />
        <el-table-column label="Imported" width="100">
          <template #default="{ row }">
            <span class="count-green">{{ row.success_count }}</span>
          </template>
        </el-table-column>
        <el-table-column label="Failed" width="90">
          <template #default="{ row }">
            <span :class="row.fail_count > 0 ? 'count-red' : 'count-muted'">{{ row.fail_count }}</span>
          </template>
        </el-table-column>
        <el-table-column label="Operator" width="140">
          <template #default="{ row }">{{ row.operator_name || 'System' }}</template>
        </el-table-column>
        <el-table-column label="Imported At" width="165" class-name="col-mono">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="Actions" width="130" align="right" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.failures?.length || row.fail_count > 0"
              link
              type="primary"
              size="small"
              @click="openFailures(row)"
            >
              View Failures
            </el-button>
            <span v-else class="count-muted">—</span>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.page_size"
        :total="batches.total"
        layout="total, prev, pager, next"
        @change="fetchBatches"
        style="margin-top:1rem; justify-content:flex-end"
      />
    </el-card>

    <template v-if="isMobile">
      <div v-loading="loadingBatches" class="mobile-list">
        <article v-for="row in batches.items" :key="row.id" class="batch-card">
          <div class="bc-head">
            <div class="bc-title">
              <div class="bc-name">{{ row.file_name }}</div>
              <div class="bc-sub">#{{ row.id }} · {{ row.operator_name || 'System' }} · {{ formatTime(row.created_at) }}</div>
            </div>
          </div>
          <div class="bc-meta">
            <div><span>Total</span>{{ row.total_count }}</div>
            <div><span>Imported</span><b class="count-green">{{ row.success_count }}</b></div>
            <div><span>Failed</span><b :class="row.fail_count > 0 ? 'count-red' : 'count-muted'">{{ row.fail_count }}</b></div>
          </div>
          <div v-if="row.failures?.length || row.fail_count > 0" class="bc-actions">
            <el-button type="primary" plain size="small" @click="openFailures(row)">View Failures</el-button>
          </div>
        </article>
        <el-empty v-if="!loadingBatches && !batches.items.length" description="No import batches yet." />
      </div>

      <el-pagination
        v-model:current-page="pagination.page"
        :page-size="pagination.page_size"
        :total="batches.total"
        layout="prev, pager, next"
        :pager-count="5"
        small
        @change="fetchBatches"
        style="margin-top:1rem; justify-content:center"
      />
    </template>

    <!-- 批次失败明细弹窗 -->
    <el-dialog
      v-model="failuresVisible"
      :title="`Import Failures · ${failuresBatch.file_name || ''}`"
      :width="isMobile ? '94%' : '620px'"
    >
      <el-table :data="failuresBatch.failures || []" size="small" border max-height="360" empty-text="No failure details recorded.">
        <el-table-column prop="row" label="Excel Row" width="110" class-name="col-mono" />
        <el-table-column prop="reason" label="Reason" min-width="240" />
      </el-table>
      <template #footer>
        <el-button @click="failuresVisible = false">Close</el-button>
      </template>
    </el-dialog>
  </AdminLayout>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, UploadFilled } from '@element-plus/icons-vue'
import AdminLayout from '../components/AdminLayout.vue'
import { useIsMobile } from '../composables/useIsMobile'
import http from '../api/http'

const isMobile = useIsMobile()

const downloadingTemplate = ref(false)
const uploadRef = ref(null)
const fileList = ref([])
const selectedFile = ref(null)
const uploading = ref(false)
const latestResult = ref(null)

const loadingBatches = ref(false)
const pagination = reactive({ page: 1, page_size: 20 })
const batches = reactive({ total: 0, items: [] })

const failuresVisible = ref(false)
const failuresBatch = ref({ file_name: '', failures: [] })

function formatTime(value) {
  return value ? String(value).replace('T', ' ').slice(0, 19) : ''
}

async function downloadTemplate() {
  downloadingTemplate.value = true
  try {
    const res = await http.get('/import/template', { responseType: 'blob' })
    const blob = res instanceof Blob
      ? res
      : new Blob([res], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'applicant_import_template.xlsx'
    document.body.appendChild(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 60000)
  } catch {
    // 错误提示由 http 响应拦截器统一处理
  } finally {
    downloadingTemplate.value = false
  }
}

function isValidXlsx(file) {
  return file?.name?.toLowerCase().endsWith('.xlsx')
}

function onFileChange(uploadFile, files) {
  if (!isValidXlsx(uploadFile)) {
    ElMessage.warning('Please select an .xlsx file.')
    fileList.value = []
    selectedFile.value = null
    return
  }
  fileList.value = files.slice(-1)
  selectedFile.value = uploadFile.raw || null
}

function onFileRemove() {
  selectedFile.value = null
}

function onFileExceed(files) {
  const next = files?.[0]
  if (!next || !isValidXlsx(next)) {
    ElMessage.warning('Please select an .xlsx file.')
    return
  }
  uploadRef.value?.clearFiles()
  uploadRef.value?.handleStart(next)
}

async function submitUpload() {
  if (!selectedFile.value) return
  uploading.value = true
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    const res = await http.post('/import/applicant', formData, { timeout: 60000 })
    latestResult.value = res.data || null
    if ((latestResult.value?.fail_count || 0) > 0) {
      ElMessage.warning(`Import finished: ${latestResult.value.success_count} imported, ${latestResult.value.fail_count} failed.`)
    } else {
      ElMessage.success(`Import completed: ${latestResult.value?.success_count ?? 0} imported.`)
    }
    uploadRef.value?.clearFiles()
    fileList.value = []
    selectedFile.value = null
    pagination.page = 1
    fetchBatches()
  } catch {
    // 错误提示由 http 响应拦截器统一处理
  } finally {
    uploading.value = false
  }
}

async function fetchBatches() {
  loadingBatches.value = true
  try {
    const res = await http.get('/import/batches', {
      params: { page: pagination.page, page_size: pagination.page_size },
    })
    batches.total = res.data?.total ?? 0
    batches.items = res.data?.items ?? []
  } finally {
    loadingBatches.value = false
  }
}

function openFailures(row) {
  failuresBatch.value = row
  failuresVisible.value = true
}

onMounted(fetchBatches)
</script>

<style scoped>
.upload-card { margin-bottom: 14px; }
.upload-area { display: flex; flex-direction: column; gap: 12px; }
.import-uploader { width: 100%; }
.import-uploader :deep(.el-upload) { width: 100%; }
.import-uploader :deep(.el-upload-dragger) { width: 100%; padding: 24px 16px; border-radius: 10px; }
.upload-actions { display: flex; justify-content: flex-end; }

.result-card { margin-bottom: 16px; }
.result-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.result-head h3 { margin: 0; font-size: 15px; font-weight: 700; color: var(--ap-ink); }
.result-file { margin: 3px 0 0; font-size: 12px; color: var(--ap-ink-soft); word-break: break-all; }
.result-time { font-family: var(--ap-mono); font-size: 11px; color: var(--ap-muted); white-space: nowrap; }

.result-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 14px; }
.stat {
  background: #f8fbfa;
  border: 1px solid var(--ap-rule-soft);
  border-radius: 10px;
  padding: 12px 14px;
}
.stat-label { display: block; font-size: 10.5px; color: var(--ap-muted); }
.stat-value {
  display: block;
  margin-top: 6px;
  font-size: 24px;
  font-weight: 700;
  line-height: 1;
  color: var(--ap-ink);
  font-variant-numeric: tabular-nums;
}
.stat-value.is-green { color: var(--ap-green); }
.stat-value.is-red { color: var(--ap-red); }
.failures-title { margin: 0 0 8px; font-size: 12px; font-weight: 700; color: var(--ap-red); }

.section-head { margin: 16px 0 10px; }
.section-head h3 { margin: 0; font-size: 15px; font-weight: 700; color: var(--ap-ink); }

.table-card :deep(.el-card__body) { padding: 0 0 12px; }
.table-card :deep(.el-pagination) { padding: 0 16px; }
.count-green { color: var(--ap-green); font-weight: 600; font-family: var(--ap-mono); }
.count-red { color: var(--ap-red); font-weight: 600; font-family: var(--ap-mono); }
.count-muted { color: var(--ap-muted); font-family: var(--ap-mono); }

.mobile-list { min-height: 100px; }
.batch-card {
  background: var(--ap-surface);
  border: 1px solid var(--ap-rule);
  border-radius: 12px;
  padding: 12px;
  margin-bottom: 10px;
  box-shadow: var(--ap-shadow);
}
.bc-name { font-size: 13.5px; font-weight: 700; color: var(--ap-ink); word-break: break-all; }
.bc-sub { font-size: 10px; color: var(--ap-muted); margin-top: 3px; font-family: var(--ap-mono); }
.bc-meta {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin: 10px 0 0;
  padding-top: 10px;
  border-top: 1px solid var(--ap-rule-soft);
  font-size: 12px;
  color: var(--ap-ink-soft);
}
.bc-meta span {
  display: block;
  font-size: 9px;
  color: var(--ap-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 2px;
}
.bc-actions { margin-top: 10px; display: flex; }
.bc-actions :deep(.el-button) { flex: 1; }

@media (max-width: 900px) {
  .result-head { flex-direction: column; gap: 4px; }
  .result-stats { gap: 6px; }
  .stat { padding: 10px; }
  .stat-value { font-size: 19px; }
  .upload-actions :deep(.el-button) { width: 100%; }
}
</style>
