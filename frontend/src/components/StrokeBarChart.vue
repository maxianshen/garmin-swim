<script setup>
import { computed } from 'vue'

const props = defineProps({
  lengths: {
    type: Array,
    default: () => [],
  },
})

const chart = computed(() => {
  const active = props.lengths.filter((l) => l.length_type_raw === 'active')
  if (!active.length) return null

  const width = 900
  const height = 260
  const padding = { top: 28, right: 52, bottom: 36, left: 44 }
  const innerW = width - padding.left - padding.right
  const innerH = height - padding.top - padding.bottom

  const maxStrokes = Math.max(...active.map((l) => l.strokes), 1)
  const swolfVals = active.map((l) => l.swolf).filter((v) => v != null)
  const hrVals = active.map((l) => l.avg_heart_rate).filter((v) => v != null)

  const minSwolf = swolfVals.length ? Math.min(...swolfVals) : 0
  const maxSwolf = swolfVals.length ? Math.max(...swolfVals) : 1
  const minHr = hrVals.length ? Math.min(...hrVals) : 0
  const maxHr = hrVals.length ? Math.max(...hrVals) : 1

  const barGap = 4
  const barWidth = Math.min(24, (innerW - barGap * (active.length - 1)) / active.length)
  const step = barWidth + barGap

  const yStroke = (v) => padding.top + innerH - (v / maxStrokes) * innerH
  const ySwolf = (v) =>
    padding.top + innerH - ((v - minSwolf) / (maxSwolf - minSwolf || 1)) * innerH
  const yHr = (v) => padding.top + innerH - ((v - minHr) / (maxHr - minHr || 1)) * innerH

  const bars = active.map((l, i) => {
    const x = padding.left + i * step
    const y = yStroke(l.strokes)
    return {
      x,
      y,
      w: barWidth,
      h: padding.top + innerH - y,
      strokes: l.strokes,
      swolf: l.swolf,
      hr: l.avg_heart_rate,
      index: l.index,
    }
  })

  const swolfPoints = active
    .map((l, i) => {
      if (l.swolf == null) return null
      const x = padding.left + i * step + barWidth / 2
      return { x, y: ySwolf(l.swolf), value: l.swolf, index: l.index }
    })
    .filter(Boolean)

  const hrPoints = active
    .map((l, i) => {
      if (l.avg_heart_rate == null) return null
      const x = padding.left + i * step + barWidth / 2
      return { x, y: yHr(l.avg_heart_rate), value: l.avg_heart_rate, index: l.index }
    })
    .filter(Boolean)

  const swolfPath = swolfPoints.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ')
  const hrPath = hrPoints.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ')

  const strokeTicks = [0, Math.round(maxStrokes / 2), maxStrokes]
  const swolfTicks = swolfVals.length
    ? [Math.round(minSwolf), Math.round((minSwolf + maxSwolf) / 2), Math.round(maxSwolf)]
    : []
  const hrTicks = hrVals.length
    ? [Math.round(minHr), Math.round((minHr + maxHr) / 2), Math.round(maxHr)]
    : []

  return {
    width,
    height,
    padding,
    innerH,
    innerW,
    bars,
    swolfPoints,
    hrPoints,
    swolfPath,
    hrPath,
    strokeTicks,
    swolfTicks,
    hrTicks,
    yStroke,
    ySwolf,
    yHr,
    maxStrokes,
    minSwolf,
    maxSwolf,
    minHr,
    maxHr,
    hasHr: hrPoints.length > 0,
    hasSwolf: swolfPoints.length > 0,
  }
})
</script>

<template>
  <div v-if="!chart" class="empty">暂无游泳趟数据</div>
  <div v-else class="chart-wrap">
    <div class="legend">
      <span class="legend-item"><i class="dot bar" />划水次数</span>
      <span v-if="chart.hasSwolf" class="legend-item"><i class="dot swolf" />SWOLF</span>
      <span v-if="chart.hasHr" class="legend-item"><i class="dot hr" />心率</span>
    </div>
    <svg :viewBox="`0 0 ${chart.width} ${chart.height}`" preserveAspectRatio="xMidYMid meet">
      <!-- grid -->
      <line
        v-for="tick in chart.strokeTicks"
        :key="'g-' + tick"
        :x1="chart.padding.left"
        :x2="chart.width - chart.padding.right"
        :y1="chart.yStroke(tick)"
        :y2="chart.yStroke(tick)"
        stroke="#243049"
        stroke-width="1"
      />

      <!-- left axis: strokes -->
      <text
        v-for="tick in chart.strokeTicks"
        :key="'ls-' + tick"
        :x="chart.padding.left - 8"
        :y="chart.yStroke(tick) + 4"
        text-anchor="end"
        fill="#3b9eff"
        font-size="10"
      >
        {{ tick }}
      </text>
      <text
        :x="14"
        :y="chart.padding.top + chart.innerH / 2"
        text-anchor="middle"
        fill="#3b9eff"
        font-size="10"
        :transform="`rotate(-90 14 ${chart.padding.top + chart.innerH / 2})`"
      >
        划水
      </text>

      <!-- right axis: SWOLF -->
      <template v-if="chart.hasSwolf">
        <text
          v-for="tick in chart.swolfTicks"
          :key="'rs-' + tick"
          :x="chart.width - chart.padding.right + 8"
          :y="chart.ySwolf(tick) + 4"
          text-anchor="start"
          fill="#fbbf24"
          font-size="10"
        >
          {{ tick }}
        </text>
      </template>

      <!-- right axis: HR (offset labels when both exist) -->
      <template v-if="chart.hasHr">
        <text
          v-for="tick in chart.hrTicks"
          :key="'rh-' + tick"
          :x="chart.width - 6"
          :y="chart.yHr(tick) + 4"
          text-anchor="end"
          fill="#f87171"
          font-size="10"
        >
          {{ tick }}
        </text>
      </template>

      <!-- bars -->
      <rect
        v-for="bar in chart.bars"
        :key="'b-' + bar.index"
        :x="bar.x"
        :y="bar.y"
        :width="bar.w"
        :height="bar.h"
        rx="3"
        fill="#3b9eff"
        opacity="0.75"
      />

      <!-- SWOLF line -->
      <path
        v-if="chart.swolfPath"
        :d="chart.swolfPath"
        fill="none"
        stroke="#fbbf24"
        stroke-width="2.5"
        stroke-linejoin="round"
        stroke-linecap="round"
      />
      <circle
        v-for="p in chart.swolfPoints"
        :key="'sw-' + p.index"
        :cx="p.x"
        :cy="p.y"
        r="3.5"
        fill="#fbbf24"
      />

      <!-- HR line -->
      <path
        v-if="chart.hrPath"
        :d="chart.hrPath"
        fill="none"
        stroke="#f87171"
        stroke-width="2.5"
        stroke-linejoin="round"
        stroke-linecap="round"
        stroke-dasharray="6 4"
      />
      <circle
        v-for="p in chart.hrPoints"
        :key="'hr-' + p.index"
        :cx="p.x"
        :cy="p.y"
        r="3.5"
        fill="#f87171"
      />

      <!-- x labels -->
      <text
        v-for="bar in chart.bars"
        :key="'xl-' + bar.index"
        :x="bar.x + bar.w / 2"
        :y="chart.height - 10"
        text-anchor="middle"
        fill="#8b9bb8"
        font-size="9"
      >
        {{ bar.index }}
      </text>
    </svg>
    <p class="caption">柱状图：划水次数 · 折线：SWOLF（黄）/ 心率（红，该趟平均）</p>
  </div>
</template>

<style scoped>
.chart-wrap {
  width: 100%;
}

.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  margin-bottom: 0.5rem;
  font-size: 0.78rem;
  color: var(--text-muted);
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 0.35rem;
}

.dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 2px;
}

.dot.bar {
  background: #3b9eff;
}

.dot.swolf {
  background: #fbbf24;
  border-radius: 50%;
}

.dot.hr {
  background: #f87171;
  border-radius: 50%;
}

svg {
  width: 100%;
  height: 260px;
  display: block;
}

.caption {
  margin-top: 0.35rem;
  font-size: 0.72rem;
  color: var(--text-muted);
  text-align: center;
}

.empty {
  padding: 1rem;
  text-align: center;
  color: var(--text-muted);
  font-size: 0.85rem;
}
</style>
