<script setup>
import { computed } from 'vue'

const props = defineProps({
  series: {
    type: Array,
    default: () => [],
  },
})

const chartData = computed(() => {
  if (!props.series.length) return null

  const width = 900
  const height = 220
  const padding = { top: 16, right: 16, bottom: 28, left: 40 }
  const innerW = width - padding.left - padding.right
  const innerH = height - padding.top - padding.bottom

  const hrs = props.series.map((p) => p.heart_rate)
  const minHr = Math.min(...hrs) - 5
  const maxHr = Math.max(...hrs) + 5

  const points = props.series.map((p, i) => {
    const x = padding.left + (i / (props.series.length - 1)) * innerW
    const y = padding.top + innerH - ((p.heart_rate - minHr) / (maxHr - minHr)) * innerH
    return { x, y, hr: p.heart_rate }
  })

  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ')
  const areaPath = `${linePath} L ${points[points.length - 1].x.toFixed(1)} ${padding.top + innerH} L ${points[0].x.toFixed(1)} ${padding.top + innerH} Z`

  const yTicks = [minHr, Math.round((minHr + maxHr) / 2), maxHr]

  return { width, height, linePath, areaPath, yTicks, padding, innerH, minHr, maxHr }
})
</script>

<template>
  <div v-if="!chartData" class="empty">暂无心率数据</div>
  <div v-else class="chart">
    <svg :viewBox="`0 0 ${chartData.width} ${chartData.height}`" preserveAspectRatio="none">
      <defs>
        <linearGradient id="hrGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#3b9eff" stop-opacity="0.35" />
          <stop offset="100%" stop-color="#3b9eff" stop-opacity="0" />
        </linearGradient>
      </defs>

      <line
        v-for="tick in chartData.yTicks"
        :key="tick"
        :x1="chartData.padding.left"
        :x2="chartData.width - chartData.padding.right"
        :y1="chartData.padding.top + chartData.innerH - ((tick - chartData.minHr) / (chartData.maxHr - chartData.minHr)) * chartData.innerH"
        :y2="chartData.padding.top + chartData.innerH - ((tick - chartData.minHr) / (chartData.maxHr - chartData.minHr)) * chartData.innerH"
        stroke="#243049"
        stroke-width="1"
      />

      <text
        v-for="tick in chartData.yTicks"
        :key="'label-' + tick"
        :x="chartData.padding.left - 6"
        :y="chartData.padding.top + chartData.innerH - ((tick - chartData.minHr) / (chartData.maxHr - chartData.minHr)) * chartData.innerH + 4"
        text-anchor="end"
        fill="#8b9bb8"
        font-size="11"
      >
        {{ tick }}
      </text>

      <path :d="chartData.areaPath" fill="url(#hrGrad)" />
      <path :d="chartData.linePath" fill="none" stroke="#3b9eff" stroke-width="2" stroke-linejoin="round" />
    </svg>
    <p class="caption">共 {{ series.length }} 个心率采样点</p>
  </div>
</template>

<style scoped>
.chart {
  width: 100%;
}

svg {
  width: 100%;
  height: 220px;
  display: block;
}

.caption {
  margin-top: 0.5rem;
  font-size: 0.8rem;
  color: var(--text-muted);
  text-align: center;
}

.empty {
  text-align: center;
  padding: 2rem;
  color: var(--text-muted);
}
</style>
