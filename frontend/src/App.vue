<script setup lang="ts">
import { onMounted, ref } from 'vue'
import type { TripPlan } from './types'
import { planTripStream } from './api'
import TripForm from './components/TripForm.vue'
import LoadingPanel from './components/LoadingPanel.vue'
import ResultView from './components/ResultView.vue'
import AmapView from './components/AmapView.vue'
import HistoryPanel from './components/HistoryPanel.vue'

type View = 'form' | 'loading' | 'result' | 'history'

/**
 * 演示模式:不用启动后端、不用配任何密钥,直接看一份完整的示例行程。
 *
 * 两个入口:
 * ① 表单页上的「先看示例行程」按钮;
 * ② URL 加 `?demo=1` 直接进入 —— 部署后可以把这个链接贴到 README 里当在线预览。
 *
 * MOCK_PLAN 用动态 import 引入,只有真的进演示模式才下载那 2KB,不影响正常访问的体积。
 */
const DEMO_QUERY = 'demo'

const view = ref<View>('form')
const plan = ref<TripPlan | null>(null)
const errorMsg = ref('')
const warnMsg = ref('')
const isMock = ref(false)
const submitting = ref(false)
/** SSE 事件流:{node, log} 逐条追加,驱动 LoadingPanel 的真实进度 */
const events = ref<{ node: string; log: string }[]>([])
/** 用户点「取消」时用它中断 fetch */
let abortCtrl: AbortController | null = null

async function handleSubmit(payload: Parameters<typeof planTripStream>[0]) {
  view.value = 'loading'
  errorMsg.value = ''
  warnMsg.value = ''
  events.value = []
  submitting.value = true
  abortCtrl = new AbortController()

  try {
    const result = await planTripStream(
      payload,
      (node, log) => events.value.push({ node, log }),
      { signal: abortCtrl.signal },
    )
    if (result.ok && result.plan) {
      plan.value = result.plan
      isMock.value = false
      // 后端重试用尽时会放行天数不符的行程;这个警告以前只写进 log 就被丢掉了
      if (result.plan.days.length !== payload.travel_days) {
        warnMsg.value = `注意:只生成了 ${result.plan.days.length} 天(请求 ${payload.travel_days} 天)`
      }
      view.value = 'result'
    } else {
      errorMsg.value = result.message || '生成失败,请重试'
      view.value = 'form'
    }
  } catch (e: any) {
    errorMsg.value = e?.message || '网络错误'
    view.value = 'form'
  } finally {
    submitting.value = false
    abortCtrl = null
  }
}

function cancelPlanning() {
  abortCtrl?.abort()
}

/** 进入演示模式:加载内置示例行程,不发任何网络请求 */
async function enterDemo() {
  const { MOCK_PLAN } = await import('./mockPlan')
  plan.value = MOCK_PLAN.data!
  isMock.value = true
  errorMsg.value = ''
  warnMsg.value = ''
  view.value = 'result'
}

/** 打开历史行程列表(数据库存档) */
function openHistory() {
  errorMsg.value = ''
  view.value = 'history'
}

/** 从历史里选中一条:复用结果页渲染 */
function showHistoryPlan(p: TripPlan) {
  plan.value = p
  isMock.value = false
  warnMsg.value = ''
  errorMsg.value = ''
  view.value = 'result'
}

// 带着 ?demo=1 打开就直接进演示(README 里的预览链接用这个)
onMounted(() => {
  if (new URLSearchParams(location.search).has(DEMO_QUERY)) enterDemo()
})

function backToForm() {
  // 清掉 ?demo=1,否则刷新页面又会跳回演示
  if (new URLSearchParams(location.search).has(DEMO_QUERY)) {
    history.replaceState(null, '', location.pathname)
    isMock.value = false
  }
  view.value = 'form'
}
</script>

<template>
  <div class="page">
    <header class="hero">
      <h1>🧭 智能旅行助手</h1>
      <p class="sub">LangGraph 多智能体规划 · 高德地图数据参考 · LLM 行程编排</p>
    </header>

    <TripForm v-if="view === 'form'" :error="errorMsg" :submitting="submitting" @submit="handleSubmit" />

    <div v-if="view === 'form'" class="demo-row">
      <button class="btn-ghost" @click="enterDemo">还没配好后端?先看一份示例行程 →</button>
      <button class="btn-ghost" @click="openHistory">🗂 历史行程</button>
      <p class="demo-hint">示例数据是内置的,不需要后端、不需要任何密钥;成功规划的行程会自动存档,可随时回看</p>
    </div>

    <LoadingPanel v-else-if="view === 'loading'" :events="events" @cancel="cancelPlanning" />

    <HistoryPanel v-else-if="view === 'history'" @close="backToForm" @view="showHistoryPlan" />

    <ResultView
      v-else-if="view === 'result' && plan"
      :plan="plan"
      :mock="isMock"
      :warning="warnMsg"
      @restart="backToForm"
    />

    <AmapView v-if="view === 'result' && plan" :plan="plan" />
  </div>
</template>

<style scoped>
.page { max-width: 960px; margin: 0 auto; padding: 24px 16px 40px; }
.hero { text-align: center; margin: 24px 0 28px; }
.hero h1 { margin: 0 0 8px; font-size: 30px; }
.sub { color: var(--muted); margin: 0; }
.demo-row { text-align: center; margin-top: 14px; }
.demo-row .btn-ghost { margin: 0 5px; }
.demo-hint { color: var(--muted); font-size: 12px; margin: 8px 0 0; }
</style>
