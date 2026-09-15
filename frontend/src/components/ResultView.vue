<script setup lang="ts">
import type { TripPlan } from '../types'
import DayCard from './DayCard.vue'
import BudgetCard from './BudgetCard.vue'

defineProps<{ plan: TripPlan; mock: boolean; warning?: string }>()
defineEmits<{ restart: [] }>()

/**
 * 后端的 Meal.type 契约是英文 breakfast/lunch/dinner,
 * 但模型偶尔会回中文,这里加一组别名兜底,避免图标静默退化成 🍽。
 */
const MEAL_ICON: Record<string, string> = {
  breakfast: '🥟', lunch: '🍜', dinner: '🍲',
  早餐: '🥟', 午餐: '🍜', 晚餐: '🍲',
}
</script>

<template>
  <div class="result">
    <div v-if="mock" class="mock-banner">当前为示例数据,启动后端后可获得真实规划</div>
    <div v-if="warning" class="warn-banner">⚠️ {{ warning }}</div>

    <div class="card header">
      <div class="title-row">
        <h2>{{ plan.city }} · {{ plan.days.length }}日游</h2>
        <span class="date">{{ plan.start_date }} ~ {{ plan.end_date }}</span>
        <button class="btn-ghost" @click="$emit('restart')">← 重新规划</button>
      </div>
      <div class="weather" v-if="plan.weather_info.length">
        <div v-for="w in plan.weather_info" :key="w.date" class="w-item">
          <div class="w-date">{{ w.date.slice(5) }}</div>
          <div>{{ w.day_weather }} {{ w.day_temp }}℃</div>
          <div class="w-night">{{ w.night_weather }} {{ w.night_temp }}℃</div>
        </div>
      </div>
      <p class="suggest" v-if="plan.overall_suggestions">💡 {{ plan.overall_suggestions }}</p>
    </div>

    <DayCard v-for="day in plan.days" :key="day.day_index" :day="day" :meal-icon="MEAL_ICON" />

    <BudgetCard v-if="plan.budget" :budget="plan.budget" />
  </div>
</template>

<style scoped>
.result { display: flex; flex-direction: column; gap: 16px; }
.mock-banner {
  background: #fef9c3; color: #854d0e;
  border-radius: 10px; padding: 10px 16px; font-size: 14px; text-align: center;
}
.warn-banner {
  background: #ffedd5; color: #9a3412;
  border-radius: 10px; padding: 10px 16px; font-size: 14px; text-align: center;
}
.title-row { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.title-row h2 { margin: 0; }
.date { color: var(--muted); }
.title-row button { margin-left: auto; }
.weather { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 14px; }
.w-item {
  background: var(--bg); border-radius: 10px;
  padding: 8px 14px; font-size: 13px; text-align: center;
}
.w-date { font-weight: 600; margin-bottom: 2px; }
.w-night { color: var(--muted); }
.suggest { margin: 14px 0 0; font-size: 14px; line-height: 1.6; }
</style>
