<script setup lang="ts">
import { ref } from 'vue'
import type { TripRequest } from '../types'

defineProps<{ error: string; submitting: boolean }>()
const emit = defineEmits<{ submit: [req: TripRequest] }>()

const city = ref('北京')

/** 用本地时区拼 YYYY-MM-DD:toISOString() 取的是 UTC 日期,北京时间早 8 点前会差一天 */
function toLocalISO(d: Date): string {
  return new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 10)
}

// 默认明天。高德天气预报只覆盖「今天起 4 天」,默认 +7 天的话行程永远没有天气
const startDate = ref(toLocalISO(new Date(Date.now() + 86400_000)))
const travelDays = ref(3)
const transportation = ref('公共交通')
const accommodation = ref('经济型酒店')
const freeText = ref('')

const PREFERENCE_OPTIONS = ['历史文化', '美食', '自然风光', '亲子', '购物', '夜生活', '博物馆', '拍照打卡']
const selectedPrefs = ref<string[]>(['历史文化'])
function togglePref(p: string) {
  const i = selectedPrefs.value.indexOf(p)
  i >= 0 ? selectedPrefs.value.splice(i, 1) : selectedPrefs.value.push(p)
}

function submit() {
  emit('submit', {
    city: city.value.trim(),
    start_date: startDate.value,
    travel_days: travelDays.value,
    transportation: transportation.value,
    accommodation: accommodation.value,
    preferences: [...selectedPrefs.value],
    other_requirements: freeText.value.trim(),
  })
}
</script>

<template>
  <form class="card form" @submit.prevent="submit">
    <div class="grid">
      <label>
        目的地城市
        <input v-model="city" required placeholder="如:北京" />
      </label>
      <label>
        出发日期
        <input v-model="startDate" type="date" required />
      </label>
      <label>
        旅行天数(1-4 天;天气只预报今天起 4 天,更远的日期不带天气)
        <input v-model.number="travelDays" type="number" min="1" max="4" required />
      </label>
      <label>
        交通方式
        <select v-model="transportation">
          <option>公共交通</option>
          <option>自驾</option>
          <option>步行优先</option>
        </select>
      </label>
      <label>
        住宿偏好
        <select v-model="accommodation">
          <option>经济型酒店</option>
          <option>舒适型酒店</option>
          <option>豪华型酒店</option>
          <option>民宿</option>
        </select>
      </label>
    </div>

    <div class="prefs">
      <span class="label">旅行偏好(可多选)</span>
      <div class="tags">
        <button
          v-for="p in PREFERENCE_OPTIONS"
          :key="p"
          type="button"
          class="tag"
          :class="{ active: selectedPrefs.includes(p) }"
          @click="togglePref(p)"
        >{{ p }}</button>
      </div>
    </div>

    <label>
      额外要求(可选)
      <textarea v-model="freeText" rows="2" placeholder="如:希望多安排博物馆,不吃辣" />
    </label>

    <p v-if="error" class="error">⚠️ {{ error }}</p>

    <button class="btn-primary" type="submit" :disabled="submitting">✨ 开始规划</button>
    <p class="hint">规划约需 20~60 秒:并行查询天气/景点/酒店 → LLM 生成行程</p>
  </form>
</template>

<style scoped>
.form { display: flex; flex-direction: column; gap: 18px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; }
label { display: flex; flex-direction: column; gap: 6px; font-size: 14px; color: var(--muted); }
.prefs .label { font-size: 14px; color: var(--muted); }
.tags { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.tag {
  border: 1px solid var(--border);
  background: #fff;
  border-radius: 999px;
  padding: 6px 14px;
  font-size: 13px;
}
.tag.active { background: var(--primary); border-color: var(--primary); color: #fff; }
.error { color: #dc2626; font-size: 14px; margin: 0; }
.hint { color: var(--muted); font-size: 12px; text-align: center; margin: 0; }
</style>
