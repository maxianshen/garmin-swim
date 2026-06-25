<script setup>
import { ref, computed, onMounted } from 'vue'
import HeartRateChart from './components/HeartRateChart.vue'
import StrokeBarChart from './components/StrokeBarChart.vue'
import ActivityList from './components/ActivityList.vue'
import TrainingAnalysis from './components/TrainingAnalysis.vue'
import TrainingCalendar from './components/TrainingCalendar.vue'

const currentView = ref('analysis')

const activities = ref([])
const activitiesLoading = ref(true)
const selectedFilename = ref(null)
const data = ref(null)
const loading = ref(false)
const error = ref(null)
const activeTab = ref('laps')
const expandedLaps = ref(new Set())
const showLapTime = ref(true)
const showLapSwolf = ref(true)

const summaryCards = computed(() => {
  if (!data.value) return []
  const s = data.value.summary
  const hasFix = (data.value.corrections?.merge_count ?? 0) > 0
  return [
    {
      label: '总距离',
      value: `${s.total_distance} m`,
      sub: hasFix ? `Garmin 记录 ${s.total_distance_raw} m` : null,
      icon: '🏊',
    },
    { label: '游泳时间', value: s.total_timer_formatted, icon: '⏱' },
    { label: '总用时', value: s.total_elapsed_formatted, icon: '🕐' },
    { label: '划水次数', value: s.total_strokes, icon: '💪' },
    { label: '卡路里', value: `${s.total_calories} kcal`, icon: '🔥' },
    { label: '平均心率', value: `${s.avg_heart_rate} bpm`, icon: '❤️' },
    { label: '最大心率', value: `${s.max_heart_rate} bpm`, icon: '📈' },
    {
      label: '平均 SWOLF',
      value: s.avg_swolf ?? '-',
      sub: hasFix ? `修正前 ${s.avg_swolf_raw}` : null,
      icon: '📐',
    },
    {
      label: '平均配速',
      value: s.avg_pace_per_100m ? `${s.avg_pace_per_100m} s/100m` : '-',
      icon: '⚡',
    },
    { label: '泳池长度', value: `${s.pool_length} m`, icon: '📏' },
    {
      label: '有效趟数',
      value: s.num_active_lengths,
      sub: hasFix ? `Garmin 记录 ${s.num_active_lengths_raw} 趟` : null,
      icon: '🔢',
    },
    { label: '训练效果', value: s.training_effect, icon: '🎯' },
    { label: '无氧效果', value: s.anaerobic_effect, icon: '💥' },
  ]
})

function formatDate(iso) {
  if (!iso) return '-'
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function toggleLap(index) {
  const next = new Set(expandedLaps.value)
  if (next.has(index)) {
    next.delete(index)
  } else {
    next.add(index)
  }
  expandedLaps.value = next
}

function isExpanded(index) {
  return expandedLaps.value.has(index)
}

async function loadActivities(options = {}) {
  activitiesLoading.value = true
  try {
    const res = await fetch('/api/activities')
    if (!res.ok) throw new Error(await res.text())
    const payload = await res.json()
    activities.value = payload.activities || []

    if (options.keepSelection && selectedFilename.value) {
      const current = activities.value.find(
        (item) => item.filename === selectedFilename.value && !item.error
      )
      if (current) return
    }

    const firstValid = activities.value.find((item) => !item.error)
    if (firstValid) {
      await selectActivity(firstValid.filename)
    } else {
      selectedFilename.value = null
      data.value = null
    }
  } catch (e) {
    error.value = e.message || '活动列表加载失败'
  } finally {
    activitiesLoading.value = false
  }
}

async function selectActivity(filename, options = {}) {
  if (!filename) return
  const force = options.force ?? false
  if (!force && selectedFilename.value === filename && data.value) return

  selectedFilename.value = filename
  if (options.tab) {
    activeTab.value = options.tab
  }
  loading.value = true
  error.value = null
  expandedLaps.value = new Set()
  try {
    const res = await fetch(`/api/activities/${encodeURIComponent(filename)}`)
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}))
      throw new Error(detail.detail || '加载活动失败')
    }
    data.value = await res.json()
  } catch (e) {
    error.value = e.message || '加载失败'
    data.value = null
  } finally {
    loading.value = false
  }
}

function openActivityFromCalendar({ filename, tab = 'laps' }) {
  currentView.value = 'analysis'
  selectActivity(filename, { tab, force: true })
}

function openPlanFromCalendar({ filename }) {
  currentView.value = 'analysis'
  selectActivity(filename, { tab: 'training', force: true })
}

async function onFileChange(event) {
  const file = event.target.files?.[0]
  if (!file) return
  loading.value = true
  error.value = null
  expandedLaps.value = new Set()
  const form = new FormData()
  form.append('file', file)
  try {
    const res = await fetch('/api/activity/upload', { method: 'POST', body: form })
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}))
      throw new Error(detail.detail || '上传解析失败')
    }
    data.value = await res.json()
    selectedFilename.value = data.value.filename
    await loadActivities({ keepSelection: true })
  } catch (e) {
    error.value = e.message || '上传失败'
  } finally {
    loading.value = false
    event.target.value = ''
  }
}

onMounted(loadActivities)
</script>

<template>
  <div class="page">
    <header class="header">
      <div>
        <p class="eyebrow">Garmin FIT 游泳活动</p>
        <h1>{{ currentView === 'calendar' ? '训练日历' : '游泳数据分析' }}</h1>
        <p v-if="currentView === 'analysis' && data" class="subtitle">
          {{ formatDate(data.summary.start_time) }}
          <span class="dot">·</span>
          {{ data.filename?.replace(/\.fit$/i, '') || '泳池游泳' }}
        </p>
        <p v-else-if="currentView === 'calendar'" class="subtitle">
          查看已完成活动与建议的下次训练计划
        </p>
      </div>
      <div class="header-actions">
        <nav class="view-nav">
          <button
            type="button"
            :class="{ active: currentView === 'analysis' }"
            @click="currentView = 'analysis'"
          >
            活动分析
          </button>
          <button
            type="button"
            :class="{ active: currentView === 'calendar' }"
            @click="currentView = 'calendar'"
          >
            训练日历
          </button>
        </nav>
        <label class="upload-btn">
          上传 .fit 文件
          <input type="file" accept=".fit" hidden @change="onFileChange" />
        </label>
      </div>
    </header>

    <TrainingCalendar
      v-if="currentView === 'calendar'"
      :selected-filename="selectedFilename"
      @open-activity="openActivityFromCalendar"
      @open-plan="openPlanFromCalendar"
    />

    <div v-else class="layout">
      <ActivityList
        :activities="activities"
        :selected="selectedFilename"
        :loading="activitiesLoading"
        @select="selectActivity"
      />

      <main class="main">
        <div v-if="loading" class="state">加载中...</div>
        <div v-else-if="error" class="state error">{{ error }}</div>
        <div v-else-if="!data" class="state">请从左侧选择活动</div>

        <template v-else>
          <div v-if="data.corrections?.merge_count" class="correction-banner">
        <strong>记圈修正</strong>
        <span>已合并 {{ data.corrections.merge_count }} 组 Garmin 误记趟数，距离减少 {{ Math.abs(data.corrections.distance_delta) }} m</span>
        <ul>
          <li v-for="group in data.corrections.merged_groups" :key="group.original_indices.join('-')">
            第 {{ group.original_indices.join('、') }} 趟均为异常片段，已合并为 1 趟
            （{{ group.strokes }} 划 / {{ group.timer_time.toFixed(1) }}s / SWOLF {{ group.swolf }}）
          </li>
        </ul>
      </div>

      <section class="cards">
        <div v-for="card in summaryCards" :key="card.label" class="card">
          <span class="card-icon">{{ card.icon }}</span>
          <div>
            <p class="card-label">{{ card.label }}</p>
            <p class="card-value">{{ card.value }}</p>
            <p v-if="card.sub" class="card-sub">{{ card.sub }}</p>
          </div>
        </div>
      </section>

      <section class="panel">
        <div class="tabs">
          <button
            :class="{ active: activeTab === 'laps' }"
            @click="activeTab = 'laps'"
          >
            分段 ({{ data.laps.length }})
          </button>
          <button
            :class="{ active: activeTab === 'hr' }"
            @click="activeTab = 'hr'"
          >
            心率曲线
          </button>
          <button
            :class="{ active: activeTab === 'training' }"
            @click="activeTab = 'training'"
          >
            训练分析
          </button>
        </div>

        <div v-show="activeTab === 'laps'" class="laps-section">
          <div class="lap-options">
            <label class="option">
              <input v-model="showLapTime" type="checkbox" />
              显示分段时间
            </label>
            <label class="option">
              <input v-model="showLapSwolf" type="checkbox" />
              显示分段 SWOLF
            </label>
          </div>

          <div class="lap-list">
            <div
              v-for="lap in data.laps"
              :key="lap.index"
              class="lap-block"
              :class="{ 'rest-block': lap.is_rest }"
            >
              <button
                class="lap-header"
                :disabled="!lap.lengths?.length"
                @click="toggleLap(lap.index)"
              >
                <span class="chevron" :class="{ open: isExpanded(lap.index) }">
                  {{ lap.lengths?.length ? '▶' : '·' }}
                </span>
                <span class="lap-num">#{{ lap.index }}</span>
                <span class="lap-stroke">{{ lap.is_rest ? '休息' : (lap.stroke || '-') }}</span>
                <span class="lap-dist">{{ lap.distance }} m</span>
                <span v-if="showLapTime" class="lap-time">{{ lap.timer_time_formatted }}</span>
                <span class="lap-strokes">{{ lap.strokes }} 划</span>
                <span v-if="showLapSwolf && !lap.is_rest" class="lap-swolf">
                  SWOLF {{ lap.avg_swolf ?? '-' }}
                </span>
                <span class="lap-hr">{{ lap.avg_heart_rate ?? '-' }} bpm</span>
              </button>

              <div v-if="isExpanded(lap.index) && lap.lengths?.length" class="lap-detail">
                <StrokeBarChart :lengths="lap.lengths" />
                <div class="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>趟</th>
                        <th>类型</th>
                        <th>泳姿</th>
                        <th>时间</th>
                        <th>划水</th>
                        <th>SWOLF</th>
                        <th>划频</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="len in lap.lengths"
                        :key="len.index"
                        :class="{
                          'rest-row': len.length_type_raw !== 'active',
                          'merged-row': len.is_corrected,
                        }"
                      >
                        <td>
                          <span>{{ len.index }}</span>
                          <span v-if="len.is_corrected" class="merge-tag" :title="len.merge_note">合并</span>
                        </td>
                        <td>{{ len.length_type }}</td>
                        <td>{{ len.stroke || '-' }}</td>
                        <td>{{ len.timer_time_formatted }}</td>
                        <td>{{ len.strokes }}</td>
                        <td>{{ len.swolf ?? '-' }}</td>
                        <td>{{ len.avg_cadence ?? '-' }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-show="activeTab === 'hr'" class="chart-wrap">
          <HeartRateChart :series="data.heart_rate_series" />
        </div>

        <div v-show="activeTab === 'training'" class="training-tab">
          <TrainingAnalysis :analysis="data.training_analysis" :activity-filename="data.filename" />
        </div>
      </section>
        </template>
      </main>
    </div>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.layout {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 1.25rem;
  align-items: start;
}

.main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

@media (max-width: 900px) {
  .layout {
    grid-template-columns: 1fr;
  }
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  flex-wrap: wrap;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.view-nav {
  display: inline-flex;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 0.2rem;
}

.view-nav button {
  background: none;
  border: none;
  color: var(--text-muted);
  padding: 0.45rem 0.85rem;
  font-size: 0.82rem;
  font-weight: 500;
  border-radius: 8px;
}

.view-nav button.active {
  background: var(--accent-soft);
  color: var(--accent);
}

.view-nav button:hover:not(.active) {
  color: var(--text);
}

.eyebrow {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--accent);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 0.25rem;
}

h1 {
  font-size: 2rem;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.subtitle {
  color: var(--text-muted);
  margin-top: 0.35rem;
  font-size: 0.95rem;
}

.dot {
  margin: 0 0.35rem;
}

.upload-btn {
  display: inline-flex;
  align-items: center;
  padding: 0.6rem 1.1rem;
  background: var(--accent-soft);
  color: var(--accent);
  border: 1px solid rgba(59, 158, 255, 0.35);
  border-radius: 10px;
  font-size: 0.875rem;
  font-weight: 600;
  transition: background 0.15s;
}

.upload-btn:hover {
  background: rgba(59, 158, 255, 0.25);
}

.state {
  text-align: center;
  padding: 3rem;
  color: var(--text-muted);
}

.state.error {
  color: #f87171;
}

.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 0.75rem;
}

.card {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 1rem;
}

.card-icon {
  font-size: 1.25rem;
}

.card-label {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-bottom: 0.15rem;
}

.card-value {
  font-size: 1.05rem;
  font-weight: 600;
}

.card-sub {
  font-size: 0.7rem;
  color: var(--warning);
  margin-top: 0.15rem;
}

.correction-banner {
  background: rgba(251, 191, 36, 0.1);
  border: 1px solid rgba(251, 191, 36, 0.35);
  border-radius: 12px;
  padding: 0.9rem 1.1rem;
  font-size: 0.875rem;
  color: var(--text);
}

.correction-banner strong {
  color: var(--warning);
  margin-right: 0.5rem;
}

.correction-banner ul {
  margin-top: 0.5rem;
  padding-left: 1.1rem;
  color: var(--text-muted);
}

.correction-banner li {
  margin-top: 0.25rem;
}

.merge-tag {
  display: inline-block;
  margin-left: 0.35rem;
  padding: 0.1rem 0.35rem;
  border-radius: 4px;
  background: rgba(251, 191, 36, 0.2);
  color: var(--warning);
  font-size: 0.65rem;
  font-weight: 600;
  vertical-align: middle;
}

.merged-row td {
  background: rgba(251, 191, 36, 0.05);
}

.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  overflow: hidden;
}

.tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--border);
  padding: 0 0.5rem;
}

.tabs button {
  background: none;
  border: none;
  color: var(--text-muted);
  padding: 0.9rem 1.1rem;
  font-size: 0.875rem;
  font-weight: 500;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition: color 0.15s;
}

.tabs button:hover {
  color: var(--text);
}

.tabs button.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}

.laps-section {
  padding: 0.75rem 0;
}

.lap-options {
  display: flex;
  gap: 1.25rem;
  padding: 0 1rem 0.75rem;
  border-bottom: 1px solid var(--border);
}

.option {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.85rem;
  color: var(--text-muted);
  cursor: pointer;
}

.option input {
  accent-color: var(--accent);
}

.lap-list {
  display: flex;
  flex-direction: column;
}

.lap-block {
  border-bottom: 1px solid var(--border);
}

.lap-block:last-child {
  border-bottom: none;
}

.rest-block .lap-header {
  opacity: 0.75;
}

.lap-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  width: 100%;
  padding: 0.85rem 1rem;
  background: none;
  border: none;
  color: var(--text);
  font-size: 0.875rem;
  text-align: left;
  transition: background 0.15s;
}

.lap-header:not(:disabled):hover {
  background: rgba(255, 255, 255, 0.03);
}

.lap-header:disabled {
  cursor: default;
}

.chevron {
  display: inline-block;
  width: 1rem;
  font-size: 0.65rem;
  color: var(--text-muted);
  transition: transform 0.2s;
}

.chevron.open {
  transform: rotate(90deg);
}

.lap-num {
  font-weight: 600;
  min-width: 2rem;
}

.lap-stroke {
  min-width: 3.5rem;
}

.lap-dist {
  min-width: 3.5rem;
  color: var(--text-muted);
}

.lap-time {
  min-width: 3rem;
  font-variant-numeric: tabular-nums;
}

.lap-strokes {
  min-width: 3.5rem;
}

.lap-swolf {
  min-width: 5rem;
  color: var(--accent);
  font-weight: 500;
}

.lap-hr {
  margin-left: auto;
  color: var(--text-muted);
}

.lap-detail {
  padding: 0 1rem 1rem 2.25rem;
  background: var(--surface-2);
  border-top: 1px solid var(--border);
}

.table-wrap {
  overflow-x: auto;
  margin-top: 0.75rem;
}

.chart-wrap {
  padding: 1.25rem;
}

.training-tab {
  padding: 0.25rem;
}
</style>
