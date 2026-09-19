<script setup lang="ts">
import { onMounted, ref } from 'vue'
import type { TripPlan, TripPlanSummary } from '../types'
import { deletePlan, getPlan, listPlans } from '../api'

/** 展示层组件:列表/删除,选中某条后把完整行程抛给父组件渲染 */
const emit = defineEmits<{ close: []; view: [plan: TripPlan] }>()

const items = ref<TripPlanSummary[]>([])
const total = ref(0)
const loading = ref(false)
const errorMsg = ref('')
const busyId = ref<number | null>(null) // 正在删除的行,防重复点击

async function refresh() {
  loading.value = true
  errorMsg.value = ''
  try {
    const resp = await listPlans({ limit: 50 })
    if (resp.success) {
      items.value = resp.items
      total.value = resp.total
    } else {
      errorMsg.value = resp.message || '加载失败'
    }
  } catch (e: any) {
    errorMsg.value = e?.message || '无法连接后端,请确认已启动'
  } finally {
    loading.value = false
  }
}

async function view(id: number) {
  errorMsg.value = ''
  try {
    const resp = await getPlan(id)
    if (resp.success && resp.data) emit('view', resp.data)
    else errorMsg.value = resp.message || '行程加载失败'
  } catch (e: any) {
    errorMsg.value = e?.message || '行程加载失败'
  }
}

async function remove(item: TripPlanSummary) {
  if (!confirm(`删除「${item.city} ${item.start_date}」的行程记录?`)) return
  busyId.value = item.id
  try {
    const resp = await deletePlan(item.id)
    if (resp.success) await refresh()
    else errorMsg.value = resp.message || '删除失败'
  } catch (e: any) {
    errorMsg.value = e?.message || '删除失败'
  } finally {
    busyId.value = null
  }
}

/** ISO 时间串 → 「2026-09-19 14:30」 */
function fmt(iso: string): string {
  return iso.slice(0, 16).replace('T', ' ')
}

onMounted(refresh)
</script>

<template>
  <div class="card history">
    <div class="head">
      <h2>🗂 历史行程<span v-if="total" class="count">(共 {{ total }} 份)</span></h2>
      <button class="btn-ghost" @click="emit('close')">← 返回</button>
    </div>

    <p v-if="loading" class="hint">加载中…</p>
    <p v-else-if="errorMsg" class="error">⚠️ {{ errorMsg }}</p>
    <p v-else-if="!items.length" class="hint">
      还没有历史行程 —— 每次成功规划都会自动存档到这里
    </p>

    <ul v-else class="list">
      <li v-for="item in items" :key="item.id" class="row">
        <div class="info">
          <div class="line1">
            <span class="city">{{ item.city }}</span>
            <span class="dates">{{ item.start_date }} ~ {{ item.end_date }} · {{ item.travel_days }}天</span>
          </div>
          <div class="line2">
            <span v-if="item.total_budget">💰 约{{ item.total_budget }}元</span>
            <span v-for="p in item.preferences" :key="p" class="pref">{{ p }}</span>
            <span class="time">{{ fmt(item.created_at) }} 保存</span>
          </div>
        </div>
        <div class="actions">
          <button class="btn-ghost small" @click="view(item.id)">查看</button>
          <button class="btn-danger small" :disabled="busyId === item.id" @click="remove(item)">
            {{ busyId === item.id ? '删除中…' : '删除' }}
          </button>
        </div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.head { display: flex; align-items: center; justify-content: space-between; }
.head h2 { margin: 0; font-size: 20px; }
.count { color: var(--muted); font-size: 14px; font-weight: normal; }
.list { list-style: none; margin: 16px 0 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
.row {
  display: flex; align-items: center; gap: 12px;
  border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px;
}
.info { flex: 1; min-width: 0; }
.line1 { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.city { font-size: 16px; font-weight: 600; }
.dates { color: var(--muted); font-size: 13px; }
.line2 { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 4px; font-size: 12px; color: var(--muted); }
.pref { background: var(--bg); border-radius: 999px; padding: 2px 8px; }
.time { margin-left: auto; }
.actions { display: flex; gap: 8px; flex-shrink: 0; }
.small { padding: 6px 12px; font-size: 13px; }
.btn-danger { background: #fff; color: #dc2626; border: 1px solid #dc2626; }
.btn-danger:disabled { opacity: 0.5; cursor: not-allowed; }
.error { color: #dc2626; font-size: 14px; }
.hint { color: var(--muted); font-size: 14px; text-align: center; margin: 18px 0 6px; }
</style>
