<script setup>
import { ref } from 'vue'

const props = defineProps({
  analysis: {
    type: Object,
    default: null,
  },
  activityFilename: {
    type: String,
    default: null,
  },
})

const downloading = ref(false)
const downloadError = ref(null)

function effectClass(value) {
  if (value == null) return ''
  if (value >= 4) return 'high'
  if (value >= 3) return 'good'
  if (value >= 2) return 'moderate'
  return 'light'
}

async function downloadWorkout() {
  if (!props.activityFilename || !props.analysis?.next_plan) return
  downloading.value = true
  downloadError.value = null
  try {
    const res = await fetch(
      `/api/activities/${encodeURIComponent(props.activityFilename)}/training-plan.fit`,
    )
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `下载失败 (${res.status})`)
    }
    const blob = await res.blob()
    const disposition = res.headers.get('Content-Disposition') || ''
    const match = disposition.match(/filename="?([^";]+)"?/)
    const filename = match?.[1] || 'swim_workout.fit'
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    downloadError.value = err.message || '下载失败'
  } finally {
    downloading.value = false
  }
}
</script>

<template>
  <section v-if="analysis" class="training-panel">
    <h3 class="panel-title">训练效果分析</h3>

    <div class="metrics">
      <div class="metric" :class="effectClass(analysis.training_effect)">
        <p class="metric-label">有氧效果</p>
        <p class="metric-value">{{ analysis.training_effect ?? '-' }}</p>
        <p class="metric-sub">{{ analysis.training_effect_label }}</p>
      </div>
      <div class="metric" :class="effectClass(analysis.anaerobic_effect)">
        <p class="metric-label">无氧效果</p>
        <p class="metric-value">{{ analysis.anaerobic_effect ?? '-' }}</p>
        <p class="metric-sub">{{ analysis.anaerobic_effect_label }}</p>
      </div>
      <div v-if="analysis.fatigue_swolf_delta != null" class="metric neutral">
        <p class="metric-label">后程 SWOLF 变化</p>
        <p class="metric-value">{{ analysis.fatigue_swolf_delta > 0 ? '+' : '' }}{{ analysis.fatigue_swolf_delta }}</p>
        <p class="metric-sub">{{ analysis.fatigue_swolf_delta > 4 ? '后段效率下降' : '较稳定' }}</p>
      </div>
      <div v-if="analysis.heart_rate_drift != null" class="metric neutral">
        <p class="metric-label">心率漂移</p>
        <p class="metric-value">{{ analysis.heart_rate_drift > 0 ? '+' : '' }}{{ analysis.heart_rate_drift }} bpm</p>
        <p class="metric-sub">后段 − 前段</p>
      </div>
      <div class="metric neutral">
        <p class="metric-label">划水稳定性</p>
        <p class="metric-value">σ {{ analysis.stroke_consistency }}</p>
        <p class="metric-sub">越小越均匀</p>
      </div>
    </div>

    <div v-if="analysis.highlights?.length" class="block">
      <h4>分析要点</h4>
      <ul>
        <li v-for="(item, i) in analysis.highlights" :key="i">{{ item }}</li>
      </ul>
    </div>

    <div v-if="analysis.suggestions?.length" class="block suggestions">
      <h4>训练建议</h4>
      <ul>
        <li v-for="(item, i) in analysis.suggestions" :key="i">{{ item }}</li>
      </ul>
    </div>

    <div v-if="analysis.next_plan" class="block next-plan">
      <div class="plan-header">
        <h4>下次训练计划</h4>
        <button
          v-if="activityFilename"
          type="button"
          class="download-btn"
          :disabled="downloading"
          @click="downloadWorkout"
        >
          {{ downloading ? '生成中…' : '下载 Garmin 训练课 (.fit)' }}
        </button>
      </div>
      <p v-if="downloadError" class="download-error">{{ downloadError }}</p>
      <p class="plan-import-hint">
        将 .fit 文件复制到手表的 GARMIN/NewFiles 文件夹，或通过 Garmin Connect 导入训练课。
      </p>
      <p class="plan-rationale">{{ analysis.next_plan.rationale }}</p>
      <p class="plan-schedule">{{ analysis.next_plan.schedule_note }}</p>

      <div class="plan-summary">
        <span class="tag primary">{{ analysis.next_plan.session_type }}</span>
        <span class="tag">{{ analysis.next_plan.total_distance }} m</span>
        <span class="tag">强度 {{ analysis.next_plan.intensity }}</span>
        <span v-if="analysis.next_plan.target_swolf" class="tag">SWOLF {{ analysis.next_plan.target_swolf }}</span>
        <span v-if="analysis.next_plan.target_heart_rate" class="tag">{{ analysis.next_plan.target_heart_rate }}</span>
        <span v-if="analysis.next_plan.target_pace" class="tag">{{ analysis.next_plan.target_pace }}</span>
      </div>
      <p class="plan-focus">重点：{{ analysis.next_plan.focus }}</p>
      <p v-if="analysis.next_plan.target_time_total_formatted" class="plan-total-time">
        预计总用时（含组间休息前游泳时间）：约 {{ analysis.next_plan.target_time_total_formatted }}
      </p>

      <div v-for="phase in analysis.next_plan.phases" :key="phase.name" class="plan-phase">
        <div class="phase-head">
          <strong>{{ phase.name }}</strong>
          <span>{{ phase.distance }} m</span>
        </div>
        <table v-if="phase.sets?.length" class="set-table">
          <thead>
            <tr>
              <th>组</th>
              <th>距离</th>
              <th>休息</th>
              <th>每组目标</th>
              <th>合计目标</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(set, i) in phase.sets" :key="i">
              <td>{{ set.reps }}×{{ set.rep_distance }} m<br /><span class="set-label">{{ set.label }}</span></td>
              <td>{{ set.distance }} m</td>
              <td>{{ set.rest || '—' }}</td>
              <td class="time">{{ set.target_time_per_rep_formatted }}</td>
              <td class="time">{{ set.target_time_total_formatted }}</td>
            </tr>
          </tbody>
        </table>
        <ul v-else-if="phase.items?.length">
          <li v-for="(item, i) in phase.items" :key="i">{{ item }}</li>
        </ul>
      </div>
    </div>
  </section>
</template>

<style scoped>
.training-panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 1.25rem 1.35rem;
}

.panel-title {
  font-size: 1rem;
  font-weight: 600;
  margin-bottom: 1rem;
}

.metrics {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
  gap: 0.75rem;
  margin-bottom: 1.25rem;
}

.metric {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 0.85rem;
}

.metric.high {
  border-color: rgba(248, 113, 113, 0.45);
}

.metric.good {
  border-color: rgba(52, 211, 153, 0.45);
}

.metric.moderate {
  border-color: rgba(59, 158, 255, 0.35);
}

.metric-label {
  font-size: 0.72rem;
  color: var(--text-muted);
  margin-bottom: 0.2rem;
}

.metric-value {
  font-size: 1.35rem;
  font-weight: 700;
}

.metric-sub {
  font-size: 0.72rem;
  color: var(--text-muted);
  margin-top: 0.15rem;
}

.block h4 {
  font-size: 0.85rem;
  font-weight: 600;
  margin-bottom: 0.5rem;
  color: var(--accent);
}

.block ul {
  padding-left: 1.1rem;
  color: var(--text);
  font-size: 0.875rem;
  line-height: 1.55;
}

.block li + li {
  margin-top: 0.35rem;
}

.suggestions {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border);
}

.suggestions h4 {
  color: var(--success);
}

.next-plan {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border);
}

.next-plan h4 {
  color: #a78bfa;
}

.plan-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
}

.plan-header h4 {
  margin-bottom: 0;
}

.download-btn {
  font-size: 0.78rem;
  padding: 0.45rem 0.85rem;
  border-radius: 8px;
  border: 1px solid rgba(167, 139, 250, 0.45);
  background: rgba(167, 139, 250, 0.12);
  color: #c4b5fd;
  cursor: pointer;
}

.download-btn:hover:not(:disabled) {
  background: rgba(167, 139, 250, 0.22);
}

.download-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.download-error {
  font-size: 0.8rem;
  color: #f87171;
  margin-bottom: 0.5rem;
}

.plan-import-hint {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-bottom: 0.75rem;
  line-height: 1.45;
}

.plan-rationale {
  font-size: 0.875rem;
  color: var(--text-muted);
  margin-bottom: 0.5rem;
  line-height: 1.5;
}

.plan-schedule {
  font-size: 0.8rem;
  color: var(--accent);
  margin-bottom: 0.75rem;
}

.plan-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.tag {
  font-size: 0.72rem;
  padding: 0.2rem 0.55rem;
  border-radius: 6px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  color: var(--text-muted);
}

.tag.primary {
  background: rgba(167, 139, 250, 0.15);
  border-color: rgba(167, 139, 250, 0.4);
  color: #c4b5fd;
  font-weight: 600;
}

.plan-focus {
  font-size: 0.85rem;
  margin-bottom: 0.5rem;
}

.plan-total-time {
  font-size: 0.82rem;
  color: var(--accent);
  margin-bottom: 1rem;
}

.plan-phase {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 0.85rem 1rem;
  margin-bottom: 0.65rem;
}

.phase-head {
  display: flex;
  justify-content: space-between;
  font-size: 0.85rem;
  margin-bottom: 0.4rem;
}

.phase-head span {
  color: var(--text-muted);
  font-size: 0.78rem;
}

.plan-phase ul {
  padding-left: 1.1rem;
  font-size: 0.84rem;
  line-height: 1.5;
  color: var(--text);
}

.plan-phase li + li {
  margin-top: 0.25rem;
}

.set-table {
  width: 100%;
  margin-top: 0.35rem;
  font-size: 0.8rem;
}

.set-table th {
  font-size: 0.7rem;
  padding: 0.45rem 0.5rem;
}

.set-table td {
  padding: 0.55rem 0.5rem;
  vertical-align: top;
}

.set-label {
  font-size: 0.72rem;
  color: var(--text-muted);
}

.set-table .time {
  font-variant-numeric: tabular-nums;
  color: #fbbf24;
  font-weight: 600;
}
</style>
