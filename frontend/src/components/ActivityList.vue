<script setup>
defineProps({
  activities: {
    type: Array,
    default: () => [],
  },
  selected: {
    type: String,
    default: null,
  },
  loading: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['select'])

function formatDate(iso) {
  if (!iso) return '未知时间'
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function displayName(filename) {
  return filename.replace(/\.fit$/i, '')
}
</script>

<template>
  <aside class="activity-list">
    <div class="list-header">
      <h2>活动列表</h2>
      <span class="count">{{ activities.length }}</span>
    </div>

    <div v-if="loading" class="list-state">加载中...</div>
    <div v-else-if="!activities.length" class="list-state">目录中暂无 .fit 文件</div>

    <ul v-else class="items">
      <li v-for="item in activities" :key="item.filename">
        <button
          class="item"
          :class="{ active: selected === item.filename, error: item.error }"
          :disabled="!!item.error"
          @click="emit('select', item.filename)"
        >
          <p class="item-title">{{ displayName(item.filename) }}</p>
          <p v-if="item.error" class="item-error">{{ item.error }}</p>
          <template v-else>
            <p class="item-date">{{ formatDate(item.start_time) }}</p>
            <div class="item-meta">
              <span>{{ item.total_distance }} m</span>
              <span>{{ item.total_timer_formatted }}</span>
            </div>
            <div class="item-meta sub">
              <span v-if="item.avg_swolf">SWOLF {{ item.avg_swolf }}</span>
              <span v-if="item.avg_heart_rate">{{ item.avg_heart_rate }} bpm</span>
              <span v-if="item.merge_count" class="fix-tag">已修正</span>
            </div>
          </template>
        </button>
      </li>
    </ul>
  </aside>
</template>

<style scoped>
.activity-list {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 320px;
}

.list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.1rem;
  border-bottom: 1px solid var(--border);
}

.list-header h2 {
  font-size: 0.95rem;
  font-weight: 600;
}

.count {
  font-size: 0.75rem;
  color: var(--text-muted);
  background: var(--surface-2);
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
}

.list-state {
  padding: 2rem 1rem;
  text-align: center;
  color: var(--text-muted);
  font-size: 0.875rem;
}

.items {
  list-style: none;
  overflow-y: auto;
  max-height: calc(100vh - 12rem);
}

.item {
  display: block;
  width: 100%;
  padding: 0.85rem 1.1rem;
  background: none;
  border: none;
  border-bottom: 1px solid var(--border);
  color: var(--text);
  text-align: left;
  transition: background 0.15s;
}

.item:last-child {
  border-bottom: none;
}

.item:not(:disabled):hover {
  background: rgba(255, 255, 255, 0.03);
}

.item.active {
  background: var(--accent-soft);
  border-left: 3px solid var(--accent);
  padding-left: calc(1.1rem - 3px);
}

.item.error {
  opacity: 0.6;
}

.item-title {
  font-size: 0.9rem;
  font-weight: 600;
  margin-bottom: 0.2rem;
  word-break: break-all;
}

.item-date {
  font-size: 0.8rem;
  color: var(--text-muted);
}

.item-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.35rem;
  font-size: 0.78rem;
  color: var(--accent);
}

.item-meta.sub {
  color: var(--text-muted);
  margin-top: 0.2rem;
}

.item-error {
  font-size: 0.75rem;
  color: #f87171;
  margin-top: 0.25rem;
}

.fix-tag {
  color: var(--warning);
}
</style>
