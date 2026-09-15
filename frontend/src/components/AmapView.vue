<script setup lang="ts">
/**
 * 高德 JS API 2.0 地图:在地图上标注每天的景点,同一天用折线连接。
 * 需要在 frontend/.env 配 VITE_AMAP_JS_KEY(「Web端(JS API)」类型 Key),
 * 未配置时整个组件不渲染,不影响其它功能。
 */
import { onMounted, ref } from 'vue'
import type { TripPlan } from '../types'

const props = defineProps<{ plan: TripPlan }>()

const DAY_COLORS = ['#2f6fed', '#16a34a', '#f59e0b', '#dc2626']
const mapEl = ref<HTMLElement | null>(null)
const failed = ref(false)

const JS_KEY = import.meta.env.VITE_AMAP_JS_KEY as string | undefined
const JS_SECRET = import.meta.env.VITE_AMAP_JS_SECRET as string | undefined

declare global {
  interface Window { AMap?: any; _AMapSecurityConfig?: { securityJsCode: string } }
}

const LOAD_TIMEOUT_MS = 10_000

function loadAMap(): Promise<any> {
  return new Promise((resolve, reject) => {
    if (window.AMap) return resolve(window.AMap)
    if (JS_SECRET) window._AMapSecurityConfig = { securityJsCode: JS_SECRET }
    const s = document.createElement('script')
    s.src = `https://webapi.amap.com/maps?v=2.0&key=${JS_KEY}`
    // 没有超时的话:脚本被墙或一直不返回时,这个 Promise 既不 resolve 也不 reject,
    // 地图区会永远空白而且不报错
    const timer = setTimeout(() => reject(new Error('高德 JS API 加载超时')), LOAD_TIMEOUT_MS)
    s.onload = () => { clearTimeout(timer); resolve(window.AMap) }
    s.onerror = () => { clearTimeout(timer); reject(new Error('高德 JS API 加载失败')) }
    document.head.appendChild(s)
  })
}

onMounted(async () => {
  if (!JS_KEY) return
  try {
    const AMap = await loadAMap()
    const points = props.plan.days.flatMap(d =>
      d.attractions.filter(a => a.location).map(a => a.location!)
    )
    if (!points.length) return

    const map = new AMap.Map(mapEl.value, {
      zoom: 11,
      center: [points[0].longitude, points[0].latitude],
    })

    props.plan.days.forEach((day, di) => {
      const color = DAY_COLORS[di % DAY_COLORS.length]
      const line: [number, number][] = []
      day.attractions.forEach((a, ai) => {
        if (!a.location) return
        line.push([a.location.longitude, a.location.latitude])
        new AMap.Marker({
          map,
          position: [a.location.longitude, a.location.latitude],
          label: { content: `D${di + 1}-${ai + 1} ${a.name}`, direction: 'top' },
        })
      })
      if (line.length > 1) {
        new AMap.Polyline({ map, path: line, strokeColor: color, strokeWeight: 4, strokeOpacity: 0.8 })
      }
    })
    map.setFitView()
  } catch {
    failed.value = true
  }
})
</script>

<template>
  <div v-if="JS_KEY" class="card map-card">
    <h3>🗺 行程地图</h3>
    <p class="legend">
      <span v-for="(d, i) in plan.days" :key="i" class="legend-item">
        <i :style="{ background: DAY_COLORS[i % DAY_COLORS.length] }" />Day {{ i + 1 }}
      </span>
    </p>
    <div v-show="!failed" ref="mapEl" class="map" />
    <p v-if="failed" class="fail">地图加载失败,请检查 JS API Key 与安全密钥配置</p>
  </div>
</template>

<style scoped>
.map-card h3 { margin: 0 0 8px; }
.legend { display: flex; gap: 16px; font-size: 13px; color: var(--muted); margin: 0 0 10px; }
.legend-item { display: inline-flex; align-items: center; gap: 5px; }
.legend-item i { width: 12px; height: 12px; border-radius: 3px; display: inline-block; }
.map { height: 380px; border-radius: 10px; }
.fail { color: #dc2626; font-size: 13px; }
</style>
