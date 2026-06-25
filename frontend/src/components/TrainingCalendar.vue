<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  selectedFilename: {
    type: String,
    default: null,
  },
})

const emit = defineEmits(['open-activity', 'open-plan'])

const loading = ref(false)
const error = ref(null)
const events = ref([])
const viewYear = ref(new Date().getFullYear())
const viewMonth = ref(new Date().getMonth() + 1)
const selectedDate = ref(null)

const weekdayLabels = ['一', '二', '三', '四', '五', '六', '日']

const monthLabel = computed(() => {
  const d = new Date(viewYear.value, viewMonth.value - 1, 1)
  return d.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long' })
})

const monthStats = computed(() => {
  const completed = events.value.filter((e) => e.type === 'completed').length
  const planned = events.value.filter((e) => e.type === 'planned').length
  return { completed, planned }
})

const eventsByDate = computed(() => {
  const map = new Map()
  for (const event of events.value) {
    const list = map.get(event.date) || []
    list.push(event)
    map.set(event.date, list)
  }
  return map
})

const calendarCells = computed(() => {
  const first = new Date(viewYear.value, viewMonth.value - 1, 1)
  const daysInMonth = new Date(viewYear.value, viewMonth.value, 0).getDate()
  const leading = (first.getDay() + 6) % 7
  const todayKey = formatDateKey(new Date())
  const cells = []

  for (let i = 0; i < leading; i += 1) {
    cells.push({ key: `pad-${i}`, empty: true })
  }

  for (let day = 1; day <= daysInMonth; day += 1) {
    const date = new Date(viewYear.value, viewMonth.value - 1, day)
    const dateKey = formatDateKey(date)
    cells.push({
      key: dateKey,
      empty: false,
      day,
      dateKey,
      isToday: dateKey === todayKey,
      events: eventsByDate.value.get(dateKey) || [],
    })
  }

  return cells
})

const selectedDayEvents = computed(() => {
  if (!selectedDate.value) return []
  return eventsByDate.value.get(selectedDate.value) || []
})

function formatDateKey(date) {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

function formatDisplayDate(dateKey) {
  if (!dateKey) return ''
  const [y, m, d] = dateKey.split('-').map(Number)
  const date = new Date(y, m - 1, d)
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    weekday: 'long',
  })
}

function formatTime(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

function shiftMonth(delta) {
  let month = viewMonth.value + delta
  let year = viewYear.value
  while (month < 1) {
    month += 12
    year -= 1
  }
  while (month > 12) {
    month -= 12
    year += 1
  }
  viewYear.value = year
  viewMonth.value = month
}

function goToday() {
  const now = new Date()
  viewYear.value = now.getFullYear()
  viewMonth.value = now.getMonth() + 1
  selectedDate.value = formatDateKey(now)
}

function selectDay(cell) {
  if (cell.empty) return
  selectedDate.value = cell.dateKey
}

function openEvent(event) {
  if (event.type === 'completed') {
    emit('open-activity', { filename: event.filename, tab: 'laps' })
    return
  }
  emit('open-plan', { filename: event.filename })
}

async function loadCalendar() {
  loading.value = true
  error.value = null
  try {
    const params = new URLSearchParams({
      year: String(viewYear.value),
      month: String(viewMonth.value),
    })
    const res = await fetch(`/api/calendar?${params}`)
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}))
      throw new Error(detail.detail || '日历加载失败')
    }
    const payload = await res.json()
    events.value = payload.events || []
    if (!selectedDate.value) {
      const today = formatDateKey(new Date())
      const inMonth = events.value.some((e) => e.date === today)
      if (inMonth || viewYear.value === new Date().getFullYear() && viewMonth.value === new Date().getMonth() + 1) {
        selectedDate.value = today
      }
    }
  } catch (err) {
    error.value = err.message || '日历加载失败'
    events.value = []
  } finally {
    loading.value = false
  }
}

watch([viewYear, viewMonth], loadCalendar, { immediate: true })
</script>

<template>
  <section class="calendar-page">
    <div class="calendar-toolbar">
      <div class="toolbar-left">
        <h2>{{ monthLabel }}</h2>
        <p class="toolbar-sub">
          本月 {{ monthStats.completed }} 次已完成
          <span class="dot">·</span>
          {{ monthStats.planned }} 项计划
        </p>
      </div>
      <div class="toolbar-actions">
        <button type="button" class="nav-btn" @click="shiftMonth(-1)">上月</button>
        <button type="button" class="nav-btn today-btn" @click="goToday">今天</button>
        <button type="button" class="nav-btn" @click="shiftMonth(1)">下月</button>
      </div>
    </div>

    <div class="legend">
      <span class="legend-item completed">已完成活动</span>
      <span class="legend-item planned">训练计划</span>
    </div>

    <div v-if="loading" class="calendar-state">加载日历中…</div>
    <div v-else-if="error" class="calendar-state error">{{ error }}</div>

    <template v-else>
      <div class="calendar-grid">
        <div v-for="label in weekdayLabels" :key="label" class="weekday">{{ label }}</div>
        <button
          v-for="cell in calendarCells"
          :key="cell.key"
          type="button"
          class="day-cell"
          :class="{
            empty: cell.empty,
            today: cell.isToday,
            selected: selectedDate === cell.dateKey,
            'has-events': cell.events?.length,
          }"
          :disabled="cell.empty"
          @click="selectDay(cell)"
        >
          <span v-if="!cell.empty" class="day-num">{{ cell.day }}</span>
          <div v-if="cell.events?.length" class="day-events">
            <span
              v-for="event in cell.events.slice(0, 3)"
              :key="event.id"
              class="event-pill"
              :class="event.type"
            >
              {{ event.type === 'completed' ? `${event.total_distance}m` : event.session_type }}
            </span>
            <span v-if="cell.events.length > 3" class="more-pill">+{{ cell.events.length - 3 }}</span>
          </div>
        </button>
      </div>

      <div class="day-detail">
        <div class="day-detail-head">
          <h3>{{ selectedDate ? formatDisplayDate(selectedDate) : '选择日期查看详情' }}</h3>
        </div>

        <div v-if="!selectedDate" class="detail-empty">点击日历中的某一天查看活动与训练计划。</div>
        <div v-else-if="!selectedDayEvents.length" class="detail-empty">这一天没有记录或计划。</div>

        <div v-else class="detail-list">
          <article
            v-for="event in selectedDayEvents"
            :key="event.id"
            class="detail-card"
            :class="[event.type, { active: selectedFilename === event.filename }]"
          >
            <div class="detail-card-head">
              <span class="detail-badge" :class="event.type">
                {{ event.type === 'completed' ? '已完成' : '训练计划' }}
              </span>
              <strong>{{ event.type === 'completed' ? event.title : event.session_type }}</strong>
            </div>

            <template v-if="event.type === 'completed'">
              <p class="detail-meta">
                {{ formatTime(event.start_time) }}
                <span class="dot">·</span>
                {{ event.total_distance }} m
                <span class="dot">·</span>
                {{ event.total_timer_formatted }}
              </p>
              <p v-if="event.avg_swolf || event.training_effect" class="detail-sub">
                <span v-if="event.avg_swolf">SWOLF {{ event.avg_swolf }}</span>
                <span v-if="event.training_effect">训练效果 {{ event.training_effect }}</span>
              </p>
            </template>

            <template v-else>
              <p class="detail-meta">
                {{ event.total_distance }} m
                <span class="dot">·</span>
                强度 {{ event.intensity }}
                <span v-if="event.target_time_total_formatted">
                  <span class="dot">·</span>
                  约 {{ event.target_time_total_formatted }}
                </span>
              </p>
              <p class="detail-sub">{{ event.focus }}</p>
              <p v-if="event.schedule_note" class="detail-note">{{ event.schedule_note }}</p>
              <p v-if="event.source_date" class="detail-note">
                基于 {{ event.source_date }} 的活动生成
              </p>
            </template>

            <button type="button" class="detail-action" @click="openEvent(event)">
              {{ event.type === 'completed' ? '查看活动' : '查看计划详情' }}
            </button>
          </article>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.calendar-page {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.calendar-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  flex-wrap: wrap;
}

.toolbar-left h2 {
  font-size: 1.5rem;
  font-weight: 700;
}

.toolbar-sub {
  color: var(--text-muted);
  font-size: 0.85rem;
  margin-top: 0.25rem;
}

.toolbar-actions {
  display: flex;
  gap: 0.5rem;
}

.nav-btn {
  padding: 0.45rem 0.85rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  font-size: 0.82rem;
}

.nav-btn:hover {
  background: var(--surface-2);
}

.today-btn {
  border-color: rgba(59, 158, 255, 0.35);
  color: var(--accent);
}

.legend {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
}

.legend-item {
  font-size: 0.78rem;
  color: var(--text-muted);
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}

.legend-item::before {
  content: '';
  width: 0.65rem;
  height: 0.65rem;
  border-radius: 999px;
}

.legend-item.completed::before {
  background: var(--success);
}

.legend-item.planned::before {
  background: #a78bfa;
}

.calendar-state {
  text-align: center;
  padding: 3rem 1rem;
  color: var(--text-muted);
}

.calendar-state.error {
  color: #f87171;
}

.calendar-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 0.5rem;
}

.weekday {
  text-align: center;
  font-size: 0.75rem;
  color: var(--text-muted);
  padding: 0.35rem 0;
}

.day-cell {
  min-height: 6.5rem;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
  padding: 0.55rem;
  text-align: left;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  transition: border-color 0.15s, background 0.15s;
}

.day-cell:not(.empty):hover {
  border-color: rgba(59, 158, 255, 0.35);
}

.day-cell.empty {
  border-color: transparent;
  background: transparent;
  cursor: default;
}

.day-cell.today {
  border-color: rgba(59, 158, 255, 0.55);
}

.day-cell.selected {
  background: var(--accent-soft);
  border-color: rgba(59, 158, 255, 0.55);
}

.day-num {
  font-size: 0.85rem;
  font-weight: 600;
}

.day-events {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.event-pill {
  font-size: 0.65rem;
  line-height: 1.2;
  padding: 0.15rem 0.35rem;
  border-radius: 5px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.event-pill.completed {
  background: rgba(52, 211, 153, 0.18);
  color: #6ee7b7;
}

.event-pill.planned {
  background: rgba(167, 139, 250, 0.18);
  color: #c4b5fd;
}

.more-pill {
  font-size: 0.62rem;
  color: var(--text-muted);
}

.day-detail {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 1rem 1.1rem;
}

.day-detail-head h3 {
  font-size: 1rem;
  font-weight: 600;
}

.detail-empty {
  margin-top: 0.75rem;
  color: var(--text-muted);
  font-size: 0.875rem;
}

.detail-list {
  display: grid;
  gap: 0.75rem;
  margin-top: 0.85rem;
}

.detail-card {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 0.9rem 1rem;
}

.detail-card.active {
  border-color: rgba(59, 158, 255, 0.45);
}

.detail-card-head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin-bottom: 0.35rem;
}

.detail-badge {
  font-size: 0.68rem;
  padding: 0.12rem 0.45rem;
  border-radius: 999px;
  font-weight: 600;
}

.detail-badge.completed {
  background: rgba(52, 211, 153, 0.15);
  color: #6ee7b7;
}

.detail-badge.planned {
  background: rgba(167, 139, 250, 0.15);
  color: #c4b5fd;
}

.detail-meta {
  font-size: 0.84rem;
  color: var(--text);
}

.detail-sub {
  margin-top: 0.25rem;
  font-size: 0.8rem;
  color: var(--text-muted);
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.detail-note {
  margin-top: 0.25rem;
  font-size: 0.78rem;
  color: var(--text-muted);
}

.detail-action {
  margin-top: 0.65rem;
  padding: 0.4rem 0.75rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--accent);
  font-size: 0.78rem;
}

.detail-action:hover {
  background: var(--accent-soft);
}

.dot {
  margin: 0 0.25rem;
}

@media (max-width: 900px) {
  .day-cell {
    min-height: 4.5rem;
  }

  .event-pill {
    font-size: 0.6rem;
  }
}
</style>
