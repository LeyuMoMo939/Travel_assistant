<script setup lang="ts">
import type { Budget } from '../types'

const props = defineProps<{ budget: Budget }>()

const items = [
  { label: '景点门票', value: props.budget.total_attractions, color: '#2f6fed' },
  { label: `住宿(${props.budget.nights}晚)`, value: props.budget.total_hotels, color: '#16a34a' },
  { label: '餐饮', value: props.budget.total_meals, color: '#f59e0b' },
]
</script>

<template>
  <div class="card budget">
    <h3>💰 预算明细</h3>
    <div class="bars">
      <div v-for="it in items" :key="it.label" class="bar-row">
        <span class="label">{{ it.label }}</span>
        <div class="track">
          <div class="fill" :style="{ width: (it.value / (budget.total || 1)) * 100 + '%', background: it.color }" />
        </div>
        <span class="num">¥{{ it.value }}</span>
      </div>
    </div>
    <div class="total">合计 <strong>¥{{ budget.total }}</strong></div>
    <p class="note">* 住宿按档位估算({{ budget.nights }} 晚 = 天数 - 1)、门票与餐饮由规划师预估,实际以出行时价格为准</p>
  </div>
</template>

<style scoped>
.budget h3 { margin: 0 0 16px; }
.note { color: var(--muted); font-size: 12px; margin: 8px 0 0; }
.bars { display: flex; flex-direction: column; gap: 10px; }
.bar-row { display: flex; align-items: center; gap: 12px; font-size: 14px; }
.label { width: 86px; color: var(--muted); }
.track { flex: 1; height: 10px; background: var(--bg); border-radius: 999px; overflow: hidden; }
.fill { height: 100%; border-radius: 999px; transition: width 0.6s ease; }
.num { width: 80px; text-align: right; }
.total { text-align: right; margin-top: 16px; font-size: 18px; }
</style>
