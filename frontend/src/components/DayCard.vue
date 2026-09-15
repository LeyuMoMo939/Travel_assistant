<script setup lang="ts">
import type { DayPlan } from '../types'

/** 每日行程卡:景点列表 + 三餐 + 酒店 */
defineProps<{ day: DayPlan; mealIcon: Record<string, string> }>()
</script>

<template>
  <div class="card day">
    <div class="head">
      <span class="badge">Day {{ day.day_index + 1 }}</span>
      <span class="date">{{ day.date }}</span>
      <span class="desc">{{ day.description }}</span>
    </div>

    <ol class="attractions">
      <li v-for="(a, i) in day.attractions" :key="a.name">
        <span class="idx">{{ i + 1 }}</span>
        <div class="info">
          <strong>{{ a.name }}</strong>
          <span class="meta">🎫 {{ a.ticket_price }}元 · ⏱ 约{{ a.visit_duration }}分钟</span>
          <span class="addr">{{ a.address }}</span>
          <p class="desc">{{ a.description }}</p>
        </div>
      </li>
    </ol>

    <div class="meals">
      <span v-for="m in day.meals" :key="m.type" class="meal">
        {{ mealIcon[m.type] || '🍽' }} <strong>{{ m.name }}</strong>({{ m.estimated_cost }}元)
      </span>
    </div>

    <div class="hotel" v-if="day.hotel">
      🏨 {{ day.hotel.name }} · 约{{ day.hotel.estimated_cost }}元/晚
    </div>
  </div>
</template>

<style scoped>
.head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 14px; }
.badge {
  background: var(--primary); color: #fff;
  border-radius: 8px; padding: 3px 10px; font-size: 13px; font-weight: 600;
}
.date { color: var(--muted); font-size: 14px; }
.desc { font-size: 14px; }
.attractions { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 12px; }
.attractions li { display: flex; gap: 12px; align-items: flex-start; }
.idx {
  flex: none; width: 26px; height: 26px;
  background: var(--bg); border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 600;
}
.info { flex: 1; display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.meta, .addr { color: var(--muted); font-size: 13px; }
.desc { margin: 2px 0 0; font-size: 13px; line-height: 1.5; }
.meals { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 14px; padding-top: 12px; border-top: 1px dashed var(--border); font-size: 13px; }
.hotel { margin-top: 10px; font-size: 13px; color: var(--muted); }
</style>
