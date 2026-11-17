<template>
  <AdminLayout active="applicant">
        <div class="page-head">
          <div>
            <h2>Applicants</h2>
            <p>Review, edit and move candidates through the hiring pipeline.</p>
          </div>
        </div>

        <!-- 统计卡片 -->
        <div class="stats">
          <div class="stat">
            <div class="stat-top">
              <span class="stat-icon"><el-icon><Calendar /></el-icon></span>
              <span class="stat-label">Today's Entries</span>
            </div>
            <span class="stat-value">{{ stats.today_total }}</span>
          </div>
          <div class="stat">
            <div class="stat-top">
              <span class="stat-icon is-amber"><el-icon><Bell /></el-icon></span>
              <span class="stat-label">New Today</span>
            </div>
            <span class="stat-value is-amber">{{ stats.today_new }}</span>
          </div>
          <div class="stat">
            <div class="stat-top">
              <span class="stat-icon is-green"><el-icon><UserFilled /></el-icon></span>
              <span class="stat-label">Total Applicants</span>
            </div>
            <span class="stat-value is-green">{{ tableData.total }}</span>
          </div>
        </div>

        <!-- 筛选区 -->
        <el-card class="filter-card">
          <el-form :inline="true" :model="filters" class="filter-form">
            <el-form-item label="Status">
              <el-select v-model="filters.status" placeholder="All" clearable style="width:140px">
                <el-option label="New" value="new" />
                <el-option label="Contacted" value="contacted" />
                <el-option label="Interview 1" value="interview1" />
                <el-option label="Interview 2" value="interview2" />
                <el-option label="Interview 3" value="interview3" />
                <el-option label="Hired" value="hired" />
                <el-option label="Lost" value="lost" />
                <el-option label="Not suitable" value="rejected" />
              </el-select>
            </el-form-item>
            <el-form-item label="Source">
              <el-select v-model="filters.source_type" placeholder="All" clearable style="width:120px">
                <el-option label="Self" value="self" />
                <el-option label="Staff" value="staff" />
                <el-option label="Referral" value="referral" />
                <el-option label="Import" value="import" />
              </el-select>
            </el-form-item>
            <el-form-item label="Keyword">
              <el-input v-model="filters.keyword" placeholder="Name / mobile number" clearable style="width:180px" />
            </el-form-item>
            <el-form-item label="Date">
              <el-date-picker v-model="filters.dateRange" type="daterange" range-separator="~" start-placeholder="Start" end-placeholder="End" value-format="YYYY-MM-DD" style="width:240px" />
            </el-form-item>
            <el-form-item class="filter-buttons">
              <el-button type="primary" @click="onSearch">Search</el-button>
              <el-button @click="resetFilters">Reset</el-button>
              <el-button @click="moreVisible = true">
                More filters{{ advancedCount ? ` (${advancedCount})` : '' }}
              </el-button>
              <el-dropdown
                v-if="isAdmin"
                split-button
                type="success"
                :disabled="exporting"
                @click="onExport(false)"
                @command="onExportCommand"
              >
                <el-icon style="margin-right:4px"><Download /></el-icon>
                {{ exporting ? 'Exporting...' : 'Export to Excel' }}
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="masked">Export masked (Default)</el-dropdown-item>
                    <el-dropdown-item command="pii">Export with full PII (Admin)</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </el-form-item>
          </el-form>

          <!-- 已生效的高级筛选：可见、可单独移除 -->
          <div v-if="activeChips.length" class="active-filters">
            <span class="chips-label">Active filters:</span>
            <el-tag
              v-for="chip in activeChips"
              :key="chip.key"
              size="small"
              closable
              @close="removeChip(chip.key)"
            >{{ chip.label }}</el-tag>
            <el-button link type="primary" size="small" @click="resetFilters">Clear all</el-button>
          </div>
        </el-card>

        <!-- 高级筛选抽屉：性别 / 年龄 -->
        <el-drawer v-model="moreVisible" title="More filters" :size="isMobile ? '100%' : '360px'">
          <el-form label-width="90px">
            <el-form-item label="Gender">
              <el-select v-model="filters.gender" placeholder="Any" clearable style="width:100%">
                <el-option label="Male" value="male" />
                <el-option label="Female" value="female" />
                <el-option label="Unspecified" value="unspecified" />
              </el-select>
            </el-form-item>
            <el-form-item label="Age">
              <div class="age-row">
                <el-input v-model.number="filters.age_min" type="number" placeholder="Min" clearable />
                <span class="age-sep">~</span>
                <el-input v-model.number="filters.age_max" type="number" placeholder="Max" clearable />
              </div>
            </el-form-item>
            <el-form-item label="Availability">
              <el-select v-model="filters.availability" placeholder="Any" clearable style="width:100%">
                <el-option label="Unknown" :value="0" />
                <el-option label="Actively looking" :value="1" />
                <el-option label="Employed" :value="2" />
                <el-option label="Not considering" :value="3" />
              </el-select>
            </el-form-item>
            <el-form-item label="Intent Tag">
              <el-input v-model="filters.intent_tag" placeholder="e.g. bpo" clearable />
            </el-form-item>
            <p class="drawer-hint">
              Age is calculated from the birth date. Applicants without a birth date are excluded when an age range is set.
            </p>
          </el-form>
          <template #footer>
            <el-button @click="clearAdvanced">Clear</el-button>
            <el-button type="primary" @click="applyAdvanced">Apply</el-button>
          </template>
        </el-drawer>

        <!-- 列表表格（桌面） -->
        <el-card v-if="!isMobile" class="table-card">
          <el-table
            ref="tableRef"
            :data="tableData.items"
            v-loading="loading"
            @row-click="onRowClick"
            @sort-change="onSortChange"
          >
            <el-table-column prop="id" label="ID" width="64" sortable="custom" class-name="col-mono" />
            <el-table-column prop="name" label="Name" min-width="170" sortable="custom">
              <template #default="{row}">
                <div class="cell-name">{{ row.first_name }} {{ row.middle_name || '' }} {{ row.last_name }}</div>
                <div class="cell-sub">{{ row.phone }}</div>
              </template>
            </el-table-column>
            <el-table-column prop="gender" label="Gender" width="88">
              <template #default="{row}">{{ genderLabel(row.gender) }}</template>
            </el-table-column>
            <el-table-column prop="birth_date" label="Age" width="60" sortable="custom">
              <template #default="{row}">{{ ageOf(row.birth_date) }}</template>
            </el-table-column>
            <el-table-column prop="target_job" label="Target Job" width="112" />
            <el-table-column prop="status" label="Status" width="118">
              <template #default="{row}">
                <span class="status-pill" :class="`is-${statusTone(row.status)}`">{{ statusLabel(row.status) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="source_type" label="Source" width="80">
              <template #default="{row}">
                <span class="source-text">{{ sourceLabel(row.source_type) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="Created At" width="138" sortable="custom" class-name="col-mono">
              <template #default="{row}">
                {{ row.created_at ? row.created_at.slice(0, 16).replace('T',' ') : '' }}
              </template>
            </el-table-column>
            <el-table-column label="Actions" width="148" fixed="right">
              <template #default="{row}">
                <el-button link type="primary" size="small" @click.stop="openDetail(row)">View</el-button>
                <el-button link type="success" size="small" @click.stop="openEdit(row)">Edit</el-button>
                <el-button link type="warning" size="small" @click.stop="openStatus(row)">Status</el-button>
              </template>
            </el-table-column>
          </el-table>

          <el-pagination
            v-model:current-page="filters.page"
            v-model:page-size="filters.page_size"
            :total="tableData.total"
            layout="total, sizes, prev, pager, next"
            :page-sizes="[10, 20, 50, 100]"
            @change="fetchList"
            style="margin-top:1rem; justify-content:flex-end"
          />
        </el-card>

        <!-- 移动端卡片列表：表格在手机上不可用，同一份数据换卡片呈现 -->
        <template v-if="isMobile">
          <div v-loading="loading" class="mobile-list">
            <article
              v-for="row in tableData.items"
              :key="row.id"
              class="applicant-card"
              @click="openDetail(row)"
            >
              <div class="ac-head">
                <span class="ac-avatar">{{ (row.first_name || '?')[0] }}{{ (row.last_name || '')[0] || '' }}</span>
                <div class="ac-id">
                  <div class="ac-name">{{ row.first_name }} {{ row.last_name }}</div>
                  <div class="ac-sub">
                    #{{ row.id }} · {{ sourceLabel(row.source_type) }} · {{ row.created_at ? row.created_at.slice(0, 10) : '' }}
                  </div>
                </div>
                <span class="status-pill" :class="`is-${statusTone(row.status)}`">{{ statusLabel(row.status) }}</span>
              </div>
              <div class="ac-meta">
                <div><span>Target job</span>{{ row.target_job || '—' }}</div>
                <div><span>Mobile</span>{{ row.phone }}</div>
                <div><span>Gender / Age</span>{{ genderLabel(row.gender) }} · {{ ageOf(row.birth_date) }}</div>
                <div><span>City</span>{{ row.address_city || '—' }}</div>
              </div>
              <div class="ac-actions" @click.stop>
                <el-button type="primary" plain size="small" @click="openDetail(row)">View</el-button>
                <el-button size="small" @click="openEdit(row)">Edit</el-button>
                <el-button type="warning" plain size="small" @click="openStatus(row)">Status</el-button>
              </div>
            </article>
            <el-empty v-if="!loading && !tableData.items.length" description="No applicants" />
          </div>

          <el-pagination
            v-model:current-page="filters.page"
            :page-size="filters.page_size"
            :total="tableData.total"
            layout="prev, pager, next"
            :pager-count="5"
            small
            @change="fetchList"
            style="margin-top:1rem; justify-content:center"
          />
        </template>

    <!-- 详情抽屉 -->
    <el-drawer v-model="detailVisible" :title="`Applicant Details #${detail.id}`" :size="isMobile ? '100%' : '680px'">
      <div v-if="detail.id" class="detail-body">
        <el-descriptions :column="isMobile ? 1 : 2" border>
          <el-descriptions-item label="Name">{{ detail.first_name }} {{ detail.middle_name || '' }} {{ detail.last_name }}</el-descriptions-item>
          <el-descriptions-item label="Gender">{{ genderLabel(detail.gender) }}</el-descriptions-item>
          <el-descriptions-item label="Birth Date">{{ detail.birth_date }}</el-descriptions-item>
          <el-descriptions-item label="Nationality">{{ detail.nationality }}</el-descriptions-item>
          <el-descriptions-item label="Marital Status">{{ titleCase(detail.marital_status) }}</el-descriptions-item>
          <el-descriptions-item label="Mobile">{{ detail.phone }}</el-descriptions-item>
          <el-descriptions-item label="Alternate No.">{{ detail.phone_alt }}</el-descriptions-item>
          <el-descriptions-item label="Email">{{ detail.email }}</el-descriptions-item>
          <el-descriptions-item label="City">{{ detail.address_city }}</el-descriptions-item>
          <el-descriptions-item label="Barangay">{{ detail.address_barangay }}</el-descriptions-item>
          <el-descriptions-item label="Home Province">{{ detail.home_province }}</el-descriptions-item>
          <el-descriptions-item label="FB Link">{{ detail.fb_profile_url }}</el-descriptions-item>
          <el-descriptions-item label="FB Name">{{ detail.fb_name }}</el-descriptions-item>
          <el-descriptions-item label="TikTok">{{ detail.tiktok_username }}</el-descriptions-item>
        </el-descriptions>

        <h4 class="detail-section-title">ID Documents</h4>
        <el-descriptions :column="isMobile ? 1 : 2" border>
          <el-descriptions-item label="ID 1">{{ detail.id1_type }} {{ detail.id1_number }}</el-descriptions-item>
          <el-descriptions-item label="NBI">{{ detail.has_nbi ? 'Yes' : 'No' }}</el-descriptions-item>
          <el-descriptions-item label="NBI Valid Until">{{ detail.nbi_valid_until }}</el-descriptions-item>
        </el-descriptions>

        <h4 class="detail-section-title">Job Preference</h4>
        <el-descriptions :column="isMobile ? 1 : 2" border>
          <el-descriptions-item label="Target Job">{{ detail.target_job }}</el-descriptions-item>
          <el-descriptions-item label="Expected Monthly Salary">{{ detail.expected_salary ? detail.expected_salary + ' PHP' : '' }}</el-descriptions-item>
          <el-descriptions-item label="Available">{{ detail.available_time }}</el-descriptions-item>
          <el-descriptions-item label="Availability">{{ availabilityLabel(detail.availability) }}</el-descriptions-item>
          <el-descriptions-item label="Available From">{{ detail.available_from }}</el-descriptions-item>
          <el-descriptions-item label="Work Type">{{ detail.work_type }}</el-descriptions-item>
          <el-descriptions-item label="Preferred Location">{{ detail.preferred_location }}</el-descriptions-item>
          <el-descriptions-item label="Intent Tags">{{ detail.intent_tags || '' }}</el-descriptions-item>
          <el-descriptions-item label="Live-in">{{ detail.live_in_ok ? 'Yes' : 'No' }}</el-descriptions-item>
        </el-descriptions>

        <h4 class="detail-section-title">Skills & Experience</h4>
        <el-descriptions :column="1" border>
          <el-descriptions-item label="Education">{{ detail.education }}</el-descriptions-item>
          <el-descriptions-item label="Skills">{{ detail.skills ? detail.skills.join(', ') : '' }}</el-descriptions-item>
          <el-descriptions-item label="English Level">{{ detail.english_level }}</el-descriptions-item>
          <el-descriptions-item label="Chinese Level">{{ detail.chinese_level }}</el-descriptions-item>
          <el-descriptions-item label="Last Job">{{ detail.last_job }}</el-descriptions-item>
          <el-descriptions-item label="Work Experience">
            <div class="multiline-text">{{ detail.work_experience }}</div>
          </el-descriptions-item>
        </el-descriptions>

        <h4 class="detail-section-title">Applicant Notes</h4>
        <div class="note-box">{{ detail.applicant_remark || 'None' }}</div>

        <h4 class="detail-section-title">Internal</h4>
        <el-descriptions :column="isMobile ? 1 : 2" border>
          <el-descriptions-item label="Status">
            <span class="status-pill" :class="`is-${statusTone(detail.status)}`">{{ statusLabel(detail.status) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="Source">{{ sourceLabel(detail.source_type) }}</el-descriptions-item>
          <el-descriptions-item label="Actual Salary">{{ detail.salary ? detail.salary + ' PHP' : '' }}</el-descriptions-item>
          <el-descriptions-item label="Employer">{{ detail.employer }}</el-descriptions-item>
          <el-descriptions-item label="Hired Date">{{ detail.hired_date }}</el-descriptions-item>
          <el-descriptions-item label="Privacy Consent">{{ detail.privacy_agreed_at ? detail.privacy_agreed_at.replace('T', ' ') : 'Not recorded' }}</el-descriptions-item>
          <el-descriptions-item label="Internal Notes">{{ detail.internal_remark || 'None' }}</el-descriptions-item>
        </el-descriptions>

        <div class="media-preview" v-if="detail.photo_oss_key || detail.video_oss_key || detail.resumes?.length || detail.resume_oss_key">
          <h4 class="detail-section-title">Media Files</h4>
          <div v-if="detail.photo_oss_key" class="media-item">
            <p class="media-label">Photo</p>
            <img :src="photoUrl" alt="photo" class="photo-preview" />
          </div>
          <div v-if="detail.video_oss_key" class="media-item">
            <p class="media-label">Self-intro Video</p>
            <video :src="videoUrl" controls class="video-preview"></video>
          </div>
          <div v-if="detail.resumes?.length" class="media-item">
            <p class="media-label">Resume Files ({{ detail.resumes.length }})</p>
            <div v-for="doc in detail.resumes" :key="doc.id" class="resume-row">
              <span class="resume-name">{{ doc.file_name }}</span>
              <span class="resume-time">{{ formatTime(doc.created_at) }}</span>
            </div>
            <el-button link type="primary" class="resume-link" @click="downloadResume">
              Download latest
            </el-button>
          </div>
          <div v-else-if="detail.resume_oss_key" class="media-item">
            <p class="media-label">Resume File</p>
            <el-button link type="primary" class="resume-link" @click="downloadResume">
              {{ detail.resume_file_name || 'Download resume' }}
            </el-button>
          </div>
        </div>

        <template v-if="detail.sources?.length">
          <h4 class="detail-section-title">Sources</h4>
          <el-descriptions :column="1" border>
            <el-descriptions-item
              v-for="source in detail.sources"
              :key="source.id"
              :label="source.platform"
            >
              {{ source.platform_profile_id || source.source_url || '-' }}
              <span class="resume-time">{{ formatTime(source.first_seen_at) }}</span>
            </el-descriptions-item>
          </el-descriptions>
        </template>

        <h4 class="detail-section-title">Contact Log</h4>
        <div class="contact-panel">
          <div class="contact-form">
            <el-select v-model="contactForm.channel" size="small" style="width:120px">
              <el-option v-for="(label, key) in channelMap" :key="key" :label="label" :value="key" />
            </el-select>
            <el-select v-model="contactForm.result" size="small" style="width:150px">
              <el-option v-for="(label, key) in resultMap" :key="key" :label="label" :value="key" />
            </el-select>
            <el-date-picker
              v-model="contactForm.next_follow_at"
              type="datetime"
              size="small"
              placeholder="Next follow-up (optional)"
              value-format="YYYY-MM-DDTHH:mm:ss"
              style="width:220px"
            />
          </div>
          <el-input
            v-model="contactForm.note"
            type="textarea"
            :rows="2"
            maxlength="500"
            placeholder="Note (optional)"
          />
          <div class="contact-actions">
            <el-button type="primary" size="small" :loading="contactSaving" @click="submitContact">
              Add contact
            </el-button>
          </div>
        </div>
        <el-timeline v-if="contacts.length">
          <el-timeline-item
            v-for="c in contacts"
            :key="c.id"
            :timestamp="formatTime(c.created_at)"
            placement="top"
          >
            <div class="history-line">
              <span class="history-operator">{{ channelLabel(c.channel) }} · {{ resultLabel(c.result) }}</span>
              <span class="history-operator">{{ c.operator_name || 'System' }}</span>
            </div>
            <div v-if="c.note" class="history-note">{{ c.note }}</div>
            <div v-if="c.next_follow_at" class="history-note">Next: {{ formatTime(c.next_follow_at) }}</div>
          </el-timeline-item>
        </el-timeline>
        <p v-else class="history-empty">No contact records yet.</p>

        <h4 class="detail-section-title">Interview Records</h4>
        <div class="contact-panel">
          <div class="contact-form">
            <el-select v-model="interviewForm.round" size="small" style="width:120px">
              <el-option label="Round 1" :value="1" />
              <el-option label="Round 2" :value="2" />
              <el-option label="Round 3" :value="3" />
            </el-select>
            <el-select v-model="interviewForm.result" size="small" style="width:130px">
              <el-option label="Pending" value="pending" />
              <el-option label="Pass" value="pass" />
              <el-option label="Fail" value="fail" />
            </el-select>
            <el-date-picker
              v-model="interviewForm.interview_at"
              type="datetime"
              size="small"
              placeholder="Interview time (optional)"
              value-format="YYYY-MM-DDTHH:mm:ss"
              style="width:220px"
            />
          </div>
          <el-input
            v-model="interviewForm.comment"
            type="textarea"
            :rows="2"
            maxlength="1000"
            placeholder="Comment (optional)"
          />
          <div class="contact-actions">
            <el-button type="primary" size="small" :loading="interviewSaving" @click="submitInterview">
              Add interview
            </el-button>
          </div>
        </div>
        <el-timeline v-if="interviews.length">
          <el-timeline-item
            v-for="iv in interviews"
            :key="iv.id"
            :timestamp="formatTime(iv.created_at)"
            placement="top"
          >
            <div class="history-line">
              <span class="status-pill" :class="`is-${interviewResultTone(iv.result)}`">
                Round {{ iv.round }} · {{ interviewResultLabel(iv.result) }}
              </span>
              <span class="history-operator">{{ iv.operator_name || 'System' }}</span>
            </div>
            <div v-if="iv.interview_at" class="history-note">Interview Time: {{ formatTime(iv.interview_at) }}</div>
            <div v-if="iv.comment" class="history-note">{{ iv.comment }}</div>
          </el-timeline-item>
        </el-timeline>
        <p v-else class="history-empty">No interview records yet.</p>

        <h4 class="detail-section-title">Status History</h4>
        <el-timeline v-if="history.length">
          <el-timeline-item
            v-for="h in history"
            :key="h.id"
            :timestamp="formatTime(h.created_at)"
            placement="top"
          >
            <div class="history-line">
              <span class="status-pill" :class="`is-${statusTone(h.to_status)}`">{{ statusLabel(h.to_status) }}</span>
              <span class="history-operator">{{ h.operator_name || 'System' }}</span>
            </div>
            <div v-if="h.note" class="history-note">{{ h.note }}</div>
          </el-timeline-item>
        </el-timeline>
        <p v-else class="history-empty">No status history yet.</p>

        <div class="detail-actions">
          <el-button type="success" plain @click="openEdit(detail)">Edit Applicant</el-button>
          <el-button v-if="isAdmin" type="danger" plain @click="onDelete">Delete Applicant</el-button>
        </div>
      </div>
    </el-drawer>

    <!-- 编辑申请人弹窗 -->
    <el-dialog v-model="editVisible" title="Edit Applicant" :width="isMobile ? '96%' : '760px'">
      <el-form :model="editForm" :label-width="isMobile ? '110px' : '130px'" :label-position="isMobile ? 'top' : 'right'">
        <el-tabs v-model="editTab">
          <el-tab-pane label="Basic & Contact" name="basic">
            <el-form-item label="Name *">
              <div class="name-row">
                <el-input v-model="editForm.first_name" placeholder="First *" />
                <el-input v-model="editForm.middle_name" placeholder="Middle" />
                <el-input v-model="editForm.last_name" placeholder="Last *" />
              </div>
            </el-form-item>
            <div class="edit-grid">
              <el-form-item label="Gender">
                <el-select v-model="editForm.gender" placeholder="Unspecified" clearable style="width:100%">
                  <el-option label="Unspecified" value="" />
                  <el-option label="Male" value="male" />
                  <el-option label="Female" value="female" />
                </el-select>
              </el-form-item>
              <el-form-item label="Birth Date">
                <el-date-picker
                  v-model="editForm.birth_date"
                  type="date"
                  placeholder="Select date"
                  value-format="YYYY-MM-DD"
                  clearable
                  style="width:100%"
                />
              </el-form-item>
              <el-form-item label="Nationality">
                <el-input v-model="editForm.nationality" placeholder="e.g. Filipino" />
              </el-form-item>
              <el-form-item label="Marital Status">
                <el-select v-model="editForm.marital_status" placeholder="Select" clearable style="width:100%">
                  <el-option label="Single" value="single" />
                  <el-option label="Married" value="married" />
                  <el-option label="Widowed" value="widowed" />
                  <el-option label="Separated" value="separated" />
                  <el-option label="Annulled" value="annulled" />
                </el-select>
              </el-form-item>
              <el-form-item label="Mobile *">
                <el-input v-model="editForm.phone" placeholder="09XXXXXXXXX" />
              </el-form-item>
              <el-form-item label="Alternate No.">
                <el-input v-model="editForm.phone_alt" placeholder="Optional" />
              </el-form-item>
              <el-form-item label="Email">
                <el-input v-model="editForm.email" placeholder="you@example.com" />
              </el-form-item>
              <el-form-item label="City">
                <el-input v-model="editForm.address_city" />
              </el-form-item>
              <el-form-item label="Barangay">
                <el-input v-model="editForm.address_barangay" />
              </el-form-item>
              <el-form-item label="Home Province">
                <el-input v-model="editForm.home_province" />
              </el-form-item>
            </div>
          </el-tab-pane>

          <el-tab-pane label="Job & Skills" name="job">
            <div class="edit-grid">
              <el-form-item label="Target Job">
                <el-input v-model="editForm.target_job" />
              </el-form-item>
              <el-form-item label="Expected Salary">
                <el-input v-model="editForm.expected_salary" type="number" min="0" placeholder="PHP / month" clearable />
              </el-form-item>
              <el-form-item label="Availability">
                <el-select v-model="editForm.availability" style="width:100%">
                  <el-option label="Unknown" :value="0" />
                  <el-option label="Actively looking" :value="1" />
                  <el-option label="Employed" :value="2" />
                  <el-option label="Not considering" :value="3" />
                </el-select>
              </el-form-item>
              <el-form-item label="Available Time">
                <el-select v-model="editForm.available_time" placeholder="Select" clearable style="width:100%">
                  <el-option label="Anytime" value="anytime" />
                  <el-option label="Within 2 weeks" value="2weeks" />
                  <el-option label="Within 1 month" value="1month" />
                </el-select>
              </el-form-item>
              <el-form-item label="Available From">
                <el-date-picker
                  v-model="editForm.available_from"
                  type="date"
                  placeholder="Select date"
                  value-format="YYYY-MM-DD"
                  clearable
                  style="width:100%"
                />
              </el-form-item>
              <el-form-item label="Work Type">
                <el-select v-model="editForm.work_type" placeholder="Select" clearable style="width:100%">
                  <el-option label="Full-time" value="fulltime" />
                  <el-option label="Part-time" value="parttime" />
                  <el-option label="Temporary" value="temp" />
                </el-select>
              </el-form-item>
              <el-form-item label="Preferred Location">
                <el-input v-model="editForm.preferred_location" />
              </el-form-item>
              <el-form-item label="Live-in OK">
                <el-select v-model="editForm.live_in_ok" style="width:100%">
                  <el-option label="Unspecified" :value="null" />
                  <el-option label="Yes" :value="true" />
                  <el-option label="No" :value="false" />
                </el-select>
              </el-form-item>
              <el-form-item label="Education">
                <el-input v-model="editForm.education" />
              </el-form-item>
              <el-form-item label="English Level">
                <el-select v-model="editForm.english_level" placeholder="Select" clearable style="width:100%">
                  <el-option label="None" value="none" />
                  <el-option label="Basic" value="basic" />
                  <el-option label="Fluent" value="fluent" />
                </el-select>
              </el-form-item>
              <el-form-item label="Chinese Level">
                <el-select v-model="editForm.chinese_level" placeholder="Select" clearable style="width:100%">
                  <el-option label="None" value="none" />
                  <el-option label="Basic" value="basic" />
                  <el-option label="Fluent" value="fluent" />
                </el-select>
              </el-form-item>
              <el-form-item label="Last Job">
                <el-input v-model="editForm.last_job" />
              </el-form-item>
            </div>
            <el-form-item label="Intent Tags">
              <el-input v-model="editForm.intent_tags" placeholder="lowercase, comma separated: bpo,cashier" />
            </el-form-item>
            <el-form-item label="Work Experience">
              <el-input v-model="editForm.work_experience" type="textarea" :rows="3" />
            </el-form-item>
          </el-tab-pane>

          <el-tab-pane label="IDs, Social & Notes" name="ids">
            <div class="edit-grid">
              <el-form-item label="ID 1 Type">
                <el-input v-model="editForm.id1_type" placeholder="e.g. UMID, Passport" />
              </el-form-item>
              <el-form-item label="ID 1 Number">
                <el-input v-model="editForm.id1_number" />
              </el-form-item>
              <el-form-item label="ID 2 Type">
                <el-input v-model="editForm.id2_type" />
              </el-form-item>
              <el-form-item label="ID 2 Number">
                <el-input v-model="editForm.id2_number" />
              </el-form-item>
              <el-form-item label="ID 3 Type">
                <el-input v-model="editForm.id3_type" />
              </el-form-item>
              <el-form-item label="ID 3 Number">
                <el-input v-model="editForm.id3_number" />
              </el-form-item>
              <el-form-item label="Has NBI">
                <el-select v-model="editForm.has_nbi" style="width:100%">
                  <el-option label="Unspecified" :value="null" />
                  <el-option label="Yes" :value="true" />
                  <el-option label="No" :value="false" />
                </el-select>
              </el-form-item>
              <el-form-item label="NBI Valid Until">
                <el-date-picker
                  v-model="editForm.nbi_valid_until"
                  type="date"
                  placeholder="Select date"
                  value-format="YYYY-MM-DD"
                  clearable
                  style="width:100%"
                />
              </el-form-item>
              <el-form-item label="FB Profile URL">
                <el-input v-model="editForm.fb_profile_url" />
              </el-form-item>
              <el-form-item label="FB Name">
                <el-input v-model="editForm.fb_name" />
              </el-form-item>
              <el-form-item label="TikTok">
                <el-input v-model="editForm.tiktok_username" placeholder="@username" />
              </el-form-item>
            </div>
            <el-form-item label="Applicant Notes">
              <el-input v-model="editForm.applicant_remark" type="textarea" :rows="3" />
            </el-form-item>
            <el-form-item label="Internal Notes">
              <el-input v-model="editForm.internal_remark" type="textarea" :rows="3" placeholder="Visible to admin only" />
            </el-form-item>
          </el-tab-pane>
        </el-tabs>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">Cancel</el-button>
        <el-button type="primary" :loading="editLoading" @click="onEditSubmit">Save</el-button>
      </template>
    </el-dialog>

    <!-- 状态流转弹窗 -->
    <el-dialog v-model="statusVisible" title="Status Change" :width="isMobile ? '94%' : '420px'">
      <el-form :model="statusForm" label-width="80px">
        <el-form-item label="Current">
          <span class="status-pill" :class="`is-${statusTone(statusForm.current)}`">{{ statusLabel(statusForm.current) }}</span>
        </el-form-item>
        <el-form-item label="New Status">
          <el-select v-model="statusForm.to_status" placeholder="Select new status" style="width:100%">
            <el-option label="New" value="new" />
            <el-option label="Contacted" value="contacted" />
            <el-option label="Interview 1" value="interview1" />
            <el-option label="Interview 2" value="interview2" />
            <el-option label="Interview 3" value="interview3" />
            <el-option label="Hired" value="hired" />
            <el-option label="Lost" value="lost" />
            <el-option label="Not suitable" value="rejected" />
          </el-select>
        </el-form-item>
        <el-form-item label="Note">
          <el-input v-model="statusForm.note" type="textarea" rows="2" placeholder="Optional note" />
        </el-form-item>
        <template v-if="statusForm.to_status === 'hired'">
          <el-form-item label="Actual Salary">
            <el-input v-model.number="statusForm.salary" type="number" placeholder="PHP" />
          </el-form-item>
          <el-form-item label="Employer">
            <el-input v-model="statusForm.employer" placeholder="Employer name" />
          </el-form-item>
          <el-form-item label="Hired Date">
            <el-date-picker v-model="statusForm.hired_date" type="date" placeholder="Select date" value-format="YYYY-MM-DD" style="width:100%" />
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="statusVisible = false">Cancel</el-button>
        <el-button type="primary" :loading="statusLoading" @click="onStatusSubmit">Confirm</el-button>
      </template>
    </el-dialog>
  </AdminLayout>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute } from 'vue-router'
import { Download, Calendar, Bell, UserFilled } from '@element-plus/icons-vue'
import AdminLayout from '../components/AdminLayout.vue'
import { useIsMobile } from '../composables/useIsMobile'
import http from '../api/http'

const isMobile = useIsMobile()
const route = useRoute()
// 删除是敏感操作，仅管理员可见
const isAdmin = computed(() => {
  try { return JSON.parse(localStorage.getItem('staff') || '{}').role === 'admin' } catch { return false }
})

// 列表数据
const loading = ref(false)
const filters = reactive({
  status: '', source_type: '', keyword: typeof route.query.keyword === 'string' ? route.query.keyword : '',
  dateRange: [],
  gender: '', age_min: '', age_max: '',
  availability: '', intent_tag: '',
  sort_by: 'created_at', order: 'desc',
  page: 1, page_size: 20,
})
const moreVisible = ref(false)
const tableRef = ref(null)
const tableData = reactive({ total: 0, items: [] })
const stats = reactive({ today_total: 0, today_new: 0 })

// 高级筛选（性别/年龄/可用性/标签）的生效状态：用于按钮计数与 chips 展示
const hasAgeRange = computed(() => filters.age_min !== '' || filters.age_max !== '')
const advancedCount = computed(() =>
  (filters.gender ? 1 : 0)
  + (hasAgeRange.value ? 1 : 0)
  + (filters.availability === '' || filters.availability === null ? 0 : 1)
  + (filters.intent_tag ? 1 : 0)
)
const activeChips = computed(() => {
  const chips = []
  if (filters.gender) {
    chips.push({ key: 'gender', label: `Gender: ${genderLabel(filters.gender)}` })
  }
  if (hasAgeRange.value) {
    const min = filters.age_min === '' ? 'any' : filters.age_min
    const max = filters.age_max === '' ? 'any' : filters.age_max
    chips.push({ key: 'age', label: `Age: ${min} ~ ${max}` })
  }
  if (filters.availability !== '' && filters.availability !== null) {
    chips.push({ key: 'availability', label: `Availability: ${availabilityLabel(filters.availability)}` })
  }
  if (filters.intent_tag) {
    chips.push({ key: 'intent_tag', label: `Tag: ${filters.intent_tag}` })
  }
  return chips
})

function genderLabel(value) {
  const map = { male: 'Male', female: 'Female' }
  return value ? (map[value] || value) : 'Unspecified'
}

// 枚举值在库里多为小写，展示时统一首字母大写
function titleCase(value) {
  return value ? String(value).charAt(0).toUpperCase() + String(value).slice(1) : ''
}

function ageOf(birthDate) {
  // 没填生日的人无法推算年龄，显示破折号而不是空白，避免看起来像加载失败
  if (!birthDate) return '—'
  const birth = new Date(birthDate)
  if (Number.isNaN(birth.getTime())) return '—'
  const today = new Date()
  let age = today.getFullYear() - birth.getFullYear()
  const monthDiff = today.getMonth() - birth.getMonth()
  if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < birth.getDate())) age -= 1
  return age
}

// 空字符串表示不筛选；数字输入被清空时不要传 0
function numOrUndefined(value) {
  if (value === '' || value === null || value === undefined) return undefined
  const num = Number(value)
  return Number.isNaN(num) ? undefined : num
}

async function fetchList() {
  loading.value = true
  try {
    const params = {
      page: filters.page,
      page_size: filters.page_size,
      status: filters.status || undefined,
      source_type: filters.source_type || undefined,
      keyword: filters.keyword || undefined,
      start_date: filters.dateRange?.[0] || undefined,
      end_date: filters.dateRange?.[1] || undefined,
      gender: filters.gender || undefined,
      age_min: numOrUndefined(filters.age_min),
      age_max: numOrUndefined(filters.age_max),
      availability: filters.availability === '' || filters.availability === null
        ? undefined
        : filters.availability,
      intent_tag: filters.intent_tag ? filters.intent_tag.trim().toLowerCase() : undefined,
      sort_by: filters.sort_by,
      order: filters.order,
    }
    const res = await http.get('/applicant/list', { params })
    tableData.total = res.data.total
    tableData.items = res.data.items
  } finally {
    loading.value = false
  }
}

function onSearch() {
  filters.page = 1
  fetchList()
}

// 表头排序：prop 与后端白名单一一对应（Age 列用 birth_date）
function onSortChange({ prop, order }) {
  if (!order) {
    filters.sort_by = 'created_at'
    filters.order = 'desc'
  } else {
    filters.sort_by = prop
    filters.order = order === 'ascending' ? 'asc' : 'desc'
  }
  filters.page = 1
  fetchList()
}

function clearAdvanced() {
  filters.gender = ''
  filters.age_min = ''
  filters.age_max = ''
  filters.availability = ''
  filters.intent_tag = ''
}

function applyAdvanced() {
  moreVisible.value = false
  filters.page = 1
  fetchList()
}

function removeChip(key) {
  if (key === 'gender') filters.gender = ''
  if (key === 'age') {
    filters.age_min = ''
    filters.age_max = ''
  }
  if (key === 'availability') filters.availability = ''
  if (key === 'intent_tag') filters.intent_tag = ''
  filters.page = 1
  fetchList()
}

async function fetchStats() {
  const res = await http.get('/applicant/stats/today')
  stats.today_total = res.data.today_total
  // 后端字段名是 today_pending（今日新增且仍待处理），与第一张卡“今日全部新增”区分
  stats.today_new = res.data.today_pending ?? 0
}

function resetFilters() {
  Object.assign(filters, {
    status: '', source_type: '', keyword: '', dateRange: [],
    gender: '', age_min: '', age_max: '',
    availability: '', intent_tag: '',
    sort_by: 'created_at', order: 'desc',
    page: 1, page_size: 20,
  })
  tableRef.value?.clearSort()
  fetchList()
}

// 状态标签映射：tone 对应 theme.css 里的彩色胶囊
const statusMap = {
  new: { label: 'New', tone: 'teal' },
  contacted: { label: 'Contacted', tone: 'amber' },
  interview1: { label: 'Interview 1', tone: 'blue' },
  interview2: { label: 'Interview 2', tone: 'blue' },
  interview3: { label: 'Interview 3', tone: 'blue' },
  hired: { label: 'Hired', tone: 'green' },
  lost: { label: 'Lost', tone: 'grey' },
  rejected: { label: 'Not suitable', tone: 'red' },
}
function statusLabel(s) { return statusMap[s]?.label || s }
function statusTone(s) { return statusMap[s]?.tone || 'grey' }

function sourceLabel(s) {
  const map = { self: 'Self', staff: 'Staff', referral: 'Referral', import: 'Import' }
  return map[s] || s
}

const availabilityMap = {
  0: 'Unknown',
  1: 'Actively looking',
  2: 'Employed',
  3: 'Not considering',
}
function availabilityLabel(value) {
  if (value === null || value === undefined || value === '') return 'Unknown'
  return availabilityMap[value] ?? String(value)
}

// 媒体文件不再公开直读：详情打开后经带 JWT 的 media-url 接口换取短时效地址
const photoUrl = ref('')
const videoUrl = ref('')

async function fetchMediaUrl(applicantId, key) {
  if (!key) return ''
  try {
    const res = await http.get(`/applicant/${applicantId}/media-url`, { params: { key } })
    return res.data?.url || ''
  } catch {
    // 无权限或文件缺失时留空，图片位显示占位
    return ''
  }
}

async function loadMediaUrls(applicantId) {
  const d = detail.value
  if (!d || d.id !== applicantId) return
  const [photo, video] = await Promise.all([
    fetchMediaUrl(applicantId, d.photo_oss_key),
    fetchMediaUrl(applicantId, d.video_oss_key),
  ])
  if (detail.value?.id === applicantId) {
    photoUrl.value = photo
    videoUrl.value = video
  }
}

// 详情
const detailVisible = ref(false)
const detail = ref({})
const history = ref([])

// 联系记录
const contacts = ref([])
const contactSaving = ref(false)
const contactForm = reactive({ channel: 'phone', result: 'reached', note: '', next_follow_at: '' })

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

async function fetchContacts(id) {
  contacts.value = []
  try {
    const res = await http.get(`/applicant/${id}/contacts`)
    contacts.value = res.data || []
  } catch {
    contacts.value = []
  }
}

async function submitContact() {
  if (!detail.value.id) return
  contactSaving.value = true
  try {
    await http.post(`/applicant/${detail.value.id}/contacts`, {
      channel: contactForm.channel,
      result: contactForm.result,
      note: trimOrNull(contactForm.note),
      next_follow_at: contactForm.next_follow_at || null,
    })
    ElMessage.success('Contact logged.')
    contactForm.note = ''
    contactForm.next_follow_at = ''
    fetchContacts(detail.value.id)
  } finally {
    contactSaving.value = false
  }
}

// 面试记录
const interviews = ref([])
const interviewSaving = ref(false)
const interviewForm = reactive({ round: 1, result: 'pending', interview_at: '', comment: '' })

const interviewResultMap = {
  pending: { label: 'Pending', tone: 'amber' },
  pass: { label: 'Pass', tone: 'green' },
  fail: { label: 'Fail', tone: 'red' },
}
function interviewResultLabel(value) { return interviewResultMap[value]?.label || value }
function interviewResultTone(value) { return interviewResultMap[value]?.tone || 'grey' }

async function fetchInterviews(id) {
  interviews.value = []
  try {
    const res = await http.get(`/applicant/${id}/interviews`)
    interviews.value = res.data || []
  } catch {
    interviews.value = []
  }
}

async function submitInterview() {
  if (!detail.value.id) return
  interviewSaving.value = true
  try {
    await http.post(`/applicant/${detail.value.id}/interviews`, {
      round: interviewForm.round,
      interview_at: interviewForm.interview_at || null,
      result: interviewForm.result,
      comment: trimOrNull(interviewForm.comment),
    })
    ElMessage.success('Interview recorded.')
    interviewForm.round = 1
    interviewForm.result = 'pending'
    interviewForm.interview_at = ''
    interviewForm.comment = ''
    fetchInterviews(detail.value.id)
  } finally {
    interviewSaving.value = false
  }
}

// 简历是私有文件：必须带 JWT 取回 blob 再触发下载，不能直接用 <a href> 打开
async function downloadResume() {
  if (!detail.value.resumes?.length && !detail.value.resume_oss_key) return
  try {
    const blob = await http.get(`/applicant/${detail.value.id}/resume`, { responseType: 'blob' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = detail.value.resumes?.[0]?.file_name
      || detail.value.resume_file_name
      || 'resume'
    document.body.appendChild(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 60000)
  } catch {
    // 错误提示由 http 响应拦截器统一处理
  }
}

function formatTime(value) {
  return value ? String(value).replace('T', ' ').slice(0, 19) : ''
}

async function fetchHistory(id) {
  history.value = []
  try {
    const res = await http.get(`/applicant/${id}/history`)
    history.value = res.data || []
  } catch {
    history.value = []
  }
}

async function openDetail(row) {
  // 先用列表行数据立即渲染，再拉详情补齐多简历与来源列表
  detail.value = row
  detailVisible.value = true
  photoUrl.value = ''
  videoUrl.value = ''
  fetchHistory(row.id)
  fetchContacts(row.id)
  fetchInterviews(row.id)
  try {
    const res = await http.get(`/applicant/${row.id}`)
    if (detail.value.id === row.id) detail.value = res.data
  } catch {
    // 详情拉取失败时保留列表行数据，不影响查看主档
  }
  loadMediaUrls(row.id)
}
function onRowClick(row) {
  openDetail(row)
}

// 编辑
const editVisible = ref(false)
const editLoading = ref(false)
const editTab = ref('basic')
const editForm = reactive({
  id: null,
  first_name: '',
  middle_name: '',
  last_name: '',
  gender: '',
  birth_date: '',
  nationality: '',
  marital_status: '',
  phone: '',
  phone_alt: '',
  email: '',
  address_city: '',
  address_barangay: '',
  home_province: '',
  target_job: '',
  expected_salary: '',
  availability: 0,
  available_time: '',
  available_from: '',
  work_type: '',
  preferred_location: '',
  intent_tags: '',
  live_in_ok: null,
  education: '',
  english_level: '',
  chinese_level: '',
  last_job: '',
  work_experience: '',
  id1_type: '',
  id1_number: '',
  id2_type: '',
  id2_number: '',
  id3_type: '',
  id3_number: '',
  has_nbi: null,
  nbi_valid_until: '',
  fb_profile_url: '',
  fb_name: '',
  tiktok_username: '',
  applicant_remark: '',
  internal_remark: '',
})

function fillEditForm(row) {
  editForm.id = row.id
  editForm.first_name = row.first_name || ''
  editForm.middle_name = row.middle_name || ''
  editForm.last_name = row.last_name || ''
  editForm.gender = row.gender || ''
  editForm.birth_date = row.birth_date || ''
  editForm.nationality = row.nationality || ''
  editForm.marital_status = row.marital_status || ''
  editForm.phone = row.phone || ''
  editForm.phone_alt = row.phone_alt || ''
  editForm.email = row.email || ''
  editForm.address_city = row.address_city || ''
  editForm.address_barangay = row.address_barangay || ''
  editForm.home_province = row.home_province || ''
  editForm.target_job = row.target_job || ''
  editForm.expected_salary = row.expected_salary ?? ''
  editForm.availability = row.availability ?? 0
  editForm.available_time = row.available_time || ''
  editForm.available_from = row.available_from || ''
  editForm.work_type = row.work_type || ''
  editForm.preferred_location = row.preferred_location || ''
  editForm.intent_tags = row.intent_tags || ''
  editForm.live_in_ok = row.live_in_ok ?? null
  editForm.education = row.education || ''
  editForm.english_level = row.english_level || ''
  editForm.chinese_level = row.chinese_level || ''
  editForm.last_job = row.last_job || ''
  editForm.work_experience = row.work_experience || ''
  editForm.id1_type = row.id1_type || ''
  editForm.id1_number = row.id1_number || ''
  editForm.id2_type = row.id2_type || ''
  editForm.id2_number = row.id2_number || ''
  editForm.id3_type = row.id3_type || ''
  editForm.id3_number = row.id3_number || ''
  editForm.has_nbi = row.has_nbi ?? null
  editForm.nbi_valid_until = row.nbi_valid_until || ''
  editForm.fb_profile_url = row.fb_profile_url || ''
  editForm.fb_name = row.fb_name || ''
  editForm.tiktok_username = row.tiktok_username || ''
  editForm.applicant_remark = row.applicant_remark || ''
  editForm.internal_remark = row.internal_remark || ''
}

async function openEdit(row) {
  editTab.value = 'basic'
  fillEditForm(row)
  editVisible.value = true
  // 表格行可能不含部分详情字段（如 work_experience / id2 / id3），从详情接口补全
  if (!('work_experience' in row) || !('id2_type' in row)) {
    try {
      const res = await http.get(`/applicant/${row.id}`)
      if (editVisible.value && editForm.id === row.id && res.data) {
        fillEditForm(res.data)
      }
    } catch {
      // 拉取失败时保留已回填字段
    }
  }
}

const trimOrNull = (v) => (typeof v === 'string' && v.trim() ? v.trim() : null)
const salaryOrNull = (v) => {
  if (v === '' || v === null || v === undefined) return null
  const num = Number(v)
  return Number.isNaN(num) ? null : Math.trunc(num)
}

async function onEditSubmit() {
  if (!editForm.first_name.trim() || !editForm.last_name.trim()) {
    ElMessage.warning('First name and last name are required.')
    return
  }
  if (!editForm.phone.trim()) {
    ElMessage.warning('Mobile number is required.')
    return
  }
  editLoading.value = true
  try {
    const payload = {
      first_name: editForm.first_name.trim(),
      middle_name: trimOrNull(editForm.middle_name),
      last_name: editForm.last_name.trim(),
      gender: trimOrNull(editForm.gender),
      birth_date: trimOrNull(editForm.birth_date),
      nationality: trimOrNull(editForm.nationality),
      marital_status: trimOrNull(editForm.marital_status),
      phone: editForm.phone.trim(),
      phone_alt: trimOrNull(editForm.phone_alt),
      email: trimOrNull(editForm.email),
      address_city: trimOrNull(editForm.address_city),
      address_barangay: trimOrNull(editForm.address_barangay),
      home_province: trimOrNull(editForm.home_province),
      target_job: trimOrNull(editForm.target_job),
      expected_salary: salaryOrNull(editForm.expected_salary),
      availability: editForm.availability,
      available_time: trimOrNull(editForm.available_time),
      available_from: trimOrNull(editForm.available_from),
      work_type: trimOrNull(editForm.work_type),
      preferred_location: trimOrNull(editForm.preferred_location),
      intent_tags: trimOrNull(editForm.intent_tags),
      live_in_ok: editForm.live_in_ok === '' || editForm.live_in_ok === undefined ? null : editForm.live_in_ok,
      education: trimOrNull(editForm.education),
      english_level: trimOrNull(editForm.english_level),
      chinese_level: trimOrNull(editForm.chinese_level),
      last_job: trimOrNull(editForm.last_job),
      work_experience: trimOrNull(editForm.work_experience),
      id1_type: trimOrNull(editForm.id1_type),
      id1_number: trimOrNull(editForm.id1_number),
      id2_type: trimOrNull(editForm.id2_type),
      id2_number: trimOrNull(editForm.id2_number),
      id3_type: trimOrNull(editForm.id3_type),
      id3_number: trimOrNull(editForm.id3_number),
      has_nbi: editForm.has_nbi === '' || editForm.has_nbi === undefined ? null : editForm.has_nbi,
      nbi_valid_until: trimOrNull(editForm.nbi_valid_until),
      fb_profile_url: trimOrNull(editForm.fb_profile_url),
      fb_name: trimOrNull(editForm.fb_name),
      tiktok_username: trimOrNull(editForm.tiktok_username),
      applicant_remark: trimOrNull(editForm.applicant_remark),
      internal_remark: trimOrNull(editForm.internal_remark),
    }
    const res = await http.patch(`/applicant/${editForm.id}`, payload)
    ElMessage.success('Saved.')
    editVisible.value = false
    // 用后端返回的权威数据刷新抽屉：手机号等字段会被服务端归一化，
    // 直接用本地 payload 覆盖会显示成 +63 917-... 这类未归一化写法
    if (detail.value.id === editForm.id && res.data) {
      detail.value = { ...detail.value, ...res.data }
    }
    fetchList()
  } finally {
    editLoading.value = false
  }
}

// 软删除（仅管理员）
async function onDelete() {
  const target = detail.value
  try {
    await ElMessageBox.confirm(
      `Delete ${target.first_name} ${target.last_name} (#${target.id})? The applicant will be hidden from the list and details. The database record will be kept.`,
      'Delete Applicant',
      { type: 'warning', confirmButtonText: 'Delete', cancelButtonText: 'Cancel' },
    )
  } catch {
    return
  }
  await http.delete(`/applicant/${target.id}`)
  ElMessage.success('Deleted.')
  detailVisible.value = false
  fetchList()
  fetchStats()
}

// 状态流转
const statusVisible = ref(false)
const statusLoading = ref(false)
const statusForm = reactive({ current: '', to_status: '', note: '', salary: null, employer: '', hired_date: '' })

function openStatus(row) {
  statusForm.current = row.status
  statusForm.to_status = ''
  statusForm.note = ''
  statusForm.salary = row.salary || null
  statusForm.employer = row.employer || ''
  statusForm.hired_date = row.hired_date || ''
  statusForm.id = row.id
  statusVisible.value = true
}

async function onStatusSubmit() {
  if (!statusForm.to_status) {
    ElMessage.warning('Please select a new status.')
    return
  }
  statusLoading.value = true
  try {
    const payload = {
      to_status: statusForm.to_status,
      note: statusForm.note || undefined,
      salary: statusForm.to_status === 'hired' ? statusForm.salary : undefined,
      employer: statusForm.to_status === 'hired' ? statusForm.employer : undefined,
      hired_date: statusForm.to_status === 'hired' ? statusForm.hired_date : undefined,
    }
    await http.patch(`/applicant/${statusForm.id}/status`, payload)
    ElMessage.success('Status updated.')
    statusVisible.value = false
    fetchList()
    fetchStats()
  } finally {
    statusLoading.value = false
  }
}

onMounted(() => { fetchList(); fetchStats() })

// 导出 Excel
const exporting = ref(false)

function parseExportFilename(disposition) {
  if (!disposition) return ''
  const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1].trim())
    } catch {
      // ignore decode error
    }
  }
  const plainMatch = disposition.match(/filename="?([^";]+)"?/i)
  return plainMatch?.[1]?.trim() || ''
}

async function onExportCommand(command) {
  if (command === 'pii') {
    try {
      await ElMessageBox.confirm(
        'This export includes unmasked PII (full mobile numbers, emails, and ID numbers) and will be recorded in the audit log. Continue?',
        'Export Full PII',
        { type: 'warning', confirmButtonText: 'Export', cancelButtonText: 'Cancel' },
      )
    } catch {
      return
    }
    await onExport(true)
    return
  }
  await onExport(false)
}

async function onExport(includePii = false) {
  exporting.value = true
  try {
    const params = {
      status: filters.status || undefined,
      source_type: filters.source_type || undefined,
      keyword: filters.keyword || undefined,
      start_date: filters.dateRange?.[0] || undefined,
      end_date: filters.dateRange?.[1] || undefined,
      gender: filters.gender || undefined,
      age_min: numOrUndefined(filters.age_min),
      age_max: numOrUndefined(filters.age_max),
      availability: filters.availability === '' || filters.availability === null
        ? undefined
        : filters.availability,
      intent_tag: filters.intent_tag ? filters.intent_tag.trim().toLowerCase() : undefined,
      include_pii: includePii,
    }
    const res = await http.get('/export/applicant', {
      params,
      responseType: 'blob',
      rawResponse: true,
    })
    const blob = res.data instanceof Blob
      ? res.data
      : new Blob([res.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = parseExportFilename(res.headers?.['content-disposition'])
      || `applicants_${new Date().toISOString().slice(0, 10)}.xlsx`
    document.body.appendChild(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(link.href), 60000)

    if (res.headers?.['x-export-truncated'] === 'true') {
      ElMessage.warning('Export reached the 10,000-row limit. Please narrow your filters to export remaining records.')
    } else {
      ElMessage.success('Export completed.')
    }
  } catch {
    // 错误提示由 http 响应拦截器统一处理
  } finally {
    exporting.value = false
  }
}
</script>

<style scoped>
/* 统计卡 */
.stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 14px; }
.stat {
  background: var(--ap-surface);
  border: 1px solid var(--ap-rule);
  border-radius: 12px;
  padding: 15px 16px;
  box-shadow: var(--ap-shadow);
}
.stat-top { display: flex; align-items: center; gap: 8px; }
.stat-icon {
  width: 26px; height: 26px; border-radius: 8px;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 13px;
  background: var(--ap-teal-soft); color: var(--ap-teal);
}
.stat-icon.is-amber { background: var(--ap-amber-soft); color: var(--ap-amber); }
.stat-icon.is-green { background: var(--ap-green-soft); color: var(--ap-green); }
.stat-label { font-size: 10.5px; color: var(--ap-muted); white-space: nowrap; }
.stat-value {
  display: block; margin-top: 10px;
  font-size: 28px; font-weight: 700; line-height: 1;
  letter-spacing: -0.02em; color: var(--ap-ink);
  font-variant-numeric: tabular-nums;
}
.stat-value.is-amber { color: var(--ap-amber); }
.stat-value.is-green { color: var(--ap-green); }

/* 筛选区 */
.filter-card { margin-bottom: 14px; }
.filter-form :deep(.el-form-item) { margin-right: 14px; margin-bottom: 0; }
.filter-buttons :deep(.el-button + .el-button) { margin-left: 0; }
.filter-buttons :deep(.el-form-item__content) { gap: 8px; }
.active-filters { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--ap-rule-soft); }
.chips-label { font-size: 11px; color: var(--ap-muted); }
.age-row { display: flex; align-items: center; gap: 8px; width: 100%; }
.age-sep { color: var(--ap-muted); }
.drawer-hint { font-size: 11px; color: var(--ap-muted); line-height: 1.6; margin: 0; }

/* 表格补充样式 */
.table-card :deep(.el-card__body) { padding: 0 0 12px; }
.table-card :deep(.el-pagination) { padding: 0 16px; }
.cell-name { font-weight: 600; color: var(--ap-ink); }
.cell-sub { font-family: var(--ap-mono); font-size: 10.5px; color: var(--ap-muted); margin-top: 2px; }
.source-text { font-size: 11px; color: var(--ap-muted); }
:deep(.el-table__cell .el-button.is-link) { font-size: 11.5px; font-weight: 600; }
:deep(.el-table__cell .el-button.is-link + .el-button.is-link) { margin-left: 8px; }

/* 详情抽屉 */
.detail-body { padding-bottom: 1.5rem; }
.detail-section-title {
  margin: 1.5rem 0 0.6rem;
  padding-top: 1rem;
  border-top: 1px solid var(--ap-rule-soft);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ap-muted);
}
.multiline-text { white-space: pre-wrap; word-break: break-word; line-height: 1.6; }
.note-box {
  background: #f8fbfa;
  border: 1px solid var(--ap-rule-soft);
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--ap-ink-soft);
  white-space: pre-wrap;
  word-break: break-word;
}
.media-preview { margin-top: 1rem; }
.media-item { margin-bottom: 1rem; }
.media-label { font-size: 11px; color: var(--ap-muted); margin: 0 0 0.5rem; }
.resume-link { color: var(--ap-teal); text-decoration: underline; word-break: break-all; font-size: 13px; }
.resume-row {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  font-size: 12px;
  padding: 4px 0;
  border-bottom: 1px dashed var(--ap-rule-soft);
}
.resume-name { color: var(--ap-ink-soft); word-break: break-all; }
.resume-time { color: var(--ap-muted); font-size: 10.5px; white-space: nowrap; }
.contact-panel { display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }
.contact-form { display: flex; gap: 8px; flex-wrap: wrap; }
.contact-actions { display: flex; justify-content: flex-end; }
.photo-preview { max-width: 200px; border-radius: 8px; border: 1px solid var(--ap-rule); }
.video-preview { max-width: 100%; max-height: 200px; border-radius: 8px; }
.detail-actions { margin-top: 1.5rem; display: flex; gap: 0.5rem; }
.history-line { display: flex; align-items: center; gap: 0.5rem; }
.history-operator { font-size: 11.5px; color: var(--ap-ink-soft); }
.history-note { font-size: 11.5px; color: var(--ap-muted); margin-top: 0.25rem; }
.history-empty { color: var(--ap-muted); font-size: 12px; margin: 0.5rem 0 0; }
.name-row { display: flex; gap: 0.5rem; width: 100%; }
.edit-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 14px; }

/* 移动端卡片列表 */
.mobile-list { min-height: 120px; }
.applicant-card {
  background: var(--ap-surface);
  border: 1px solid var(--ap-rule);
  border-radius: 12px;
  padding: 12px;
  margin-bottom: 10px;
  box-shadow: var(--ap-shadow);
}
.ac-head { display: flex; align-items: center; gap: 10px; }
.ac-avatar {
  width: 36px; height: 36px; border-radius: 50%;
  background: var(--ap-teal-soft); color: var(--ap-teal);
  font-size: 11px; font-weight: 700; text-transform: uppercase;
  display: inline-flex; align-items: center; justify-content: center;
  flex: 0 0 auto;
}
.ac-id { min-width: 0; flex: 1; }
.ac-name {
  font-size: 14px; font-weight: 700; color: var(--ap-ink);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.ac-sub { font-size: 9.5px; color: var(--ap-muted); margin-top: 2px; }
.ac-head .status-pill { margin-left: auto; flex: 0 0 auto; }
.ac-meta {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 7px 10px;
  margin: 11px 0 10px;
  padding: 10px 0;
  border-top: 1px solid var(--ap-rule-soft);
  border-bottom: 1px solid var(--ap-rule-soft);
  font-size: 11.5px;
  color: var(--ap-ink-soft);
}
.ac-meta span {
  display: block;
  font-size: 8.5px;
  color: var(--ap-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 1px;
}
.ac-actions { display: flex; gap: 7px; }
.ac-actions :deep(.el-button) { flex: 1; margin-left: 0; }

@media (max-width: 900px) {
  .stats { gap: 6px; margin-bottom: 12px; }
  .stat { padding: 10px 9px; border-radius: 10px; }
  .stat-top { gap: 5px; }
  .stat-icon { width: 20px; height: 20px; border-radius: 6px; font-size: 10px; }
  .stat-label { font-size: 8.5px; }
  .stat-value { font-size: 19px; margin-top: 7px; }
  .filter-form :deep(.el-form-item) {
    display: block;
    width: 100%;
    margin-right: 0;
    margin-bottom: 10px;
  }
  .filter-form :deep(.el-form-item__content) { width: 100%; }
  .filter-form :deep(.el-input),
  .filter-form :deep(.el-select),
  .filter-form :deep(.el-date-editor) { width: 100% !important; }
  .filter-buttons :deep(.el-form-item__content) {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
  .filter-buttons :deep(.el-button) { flex: 1 1 45%; margin-left: 0; }
  .name-row { flex-direction: column; }
  .edit-grid { grid-template-columns: 1fr; }
  .detail-actions { flex-wrap: wrap; }
  .photo-preview { max-width: 100%; }
}
</style>
