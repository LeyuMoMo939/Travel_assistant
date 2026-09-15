<script setup lang="ts">
import { computed } from 'vue'

/**
 * 真实进度面板:events 数组由后端 SSE 事件驱动(App.vue 逐条追加),
 * 每个节点完成时它对应的行打勾 —— 不再用定时器假装进度。
 */
const props = defineProps<{ events: { node: string; log: string }[] }>()
const emit = defineEmits<{ cancel: [] }>()

const STAGES = [
  { node: 'weather', label: '🌤 查询目的地天气' },
  { node: 'attractions', label: '📍 搜索候选景点' },
  { node: 'hotels', label: '🏨 搜索候选酒店' },
  { node: 'planner', label: '📋 旅行规划师生成行程(LLM,最耗时)' },
  { node: 'validate', label: '🔍 校验行程完整性(不合格会自动重试)' },
  { node: 'budget', label: '💰 精确计算预算' },
]

const doneByNode = computed(() => {
  const m = new Map<string, string>()
  for (const e of props.events) m.set(e.node, e.log)
  return m
})
</script>

<template>
  <div class="card loading">
    <div class="spinner" />
    <h2>正在为你规划旅程…</h2>
    <ul>
      <li v-for="s in STAGES" :key="s.node" :class="{ done: doneByNode.has(s.node) }">
        <span class="mark">{{ doneByNode.has(s.node) ? '✅' : '⏳' }}</span>
        <span>
          {{ s.label }}
          <small v-if="doneByNode.get(s.node)" class="server-log">{{ doneByNode.get(s.node) }}</small>
        </span>
      </li>
    </ul>
    <p class="tip">前三个节点由 LangGraph 并行执行,谁先完成谁先打勾</p>
    <button class="btn-ghost cancel" @click="emit('cancel')">取消规划</button>
  </div>
</template>

<style scoped>
.loading { text-align: center; padding: 40px 20px; }
.spinner {
  width: 42px; height: 42px;
  margin: 0 auto 16px;
  border: 4px solid var(--border);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
ul { list-style: none; padding: 0; max-width: 520px; margin: 20px auto; text-align: left; }
li { padding: 7px 0; color: var(--muted); }
li.done { color: #16a34a; }
.mark { margin-right: 8px; }
.server-log { display: block; color: var(--muted); font-size: 12px; margin-left: 24px; }
.tip { color: var(--muted); font-size: 12px; }
.cancel { margin-top: 6px; }
</style>
