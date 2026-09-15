import type { TripPlan, TripRequest } from './types'

/** SSE 流式事件的结构(与后端 api/server.py 的 event_gen 对应) */
interface StreamResult {
  ok: boolean
  plan?: TripPlan
  message?: string
  logs: string[]
}

/** 默认 3 分钟:最慢的是 planner 节点的 LLM 调用(SDK 单次超时 120s,还会重试) */
const DEFAULT_TIMEOUT_MS = 180_000

/**
 * 调用后端 /api/plan/stream(SSE 流式),每收到一个节点完成事件就回调 onNode,
 * 进度条因此和真实执行进度同步。EventSource 不支持 POST,所以用 fetch 手动读流。
 *
 * options.signal 用于「取消」;超时由内部 AbortController 控制。
 */
export async function planTripStream(
  req: TripRequest,
  onNode: (node: string, log: string) => void,
  options: { signal?: AbortSignal; timeoutMs?: number } = {},
): Promise<StreamResult> {
  const ctrl = new AbortController()
  const abort = () => ctrl.abort()
  options.signal?.addEventListener('abort', abort, { once: true })
  const timer = setTimeout(abort, options.timeoutMs ?? DEFAULT_TIMEOUT_MS)

  try {
    const resp = await fetch('/api/plan/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
      signal: ctrl.signal,
    })
    if (!resp.ok || !resp.body) throw new Error(await describeHttpError(resp))
    return await readEventStream(resp.body, onNode)
  } catch (e) {
    // 用户点了取消
    if (options.signal?.aborted) throw new Error('已取消规划')
    // 超时:内部 abort 触发,外部 signal 没有
    if (ctrl.signal.aborted) throw new Error('等待超时(后端超过 3 分钟无响应),请重试')
    // fetch 在网络层失败时抛 TypeError
    if (e instanceof TypeError) throw new Error('无法连接后端,请确认已启动(uvicorn api.server:app)')
    throw e
  } finally {
    clearTimeout(timer)
    options.signal?.removeEventListener('abort', abort)
  }
}

/** 把 FastAPI 的错误响应转成人能看懂的一句话 */
async function describeHttpError(resp: Response): Promise<string> {
  let detail = ''
  try {
    const body = await resp.json()
    // FastAPI 的 422 里 detail 是对象数组,其它情况通常是字符串
    detail = typeof body?.detail === 'string' ? body.detail : JSON.stringify(body?.detail ?? body)
  } catch {
    /* 响应体不是 JSON(例如 502 的 HTML 错误页),忽略 */
  }
  return detail
    ? `请求被拒绝(${resp.status}):${detail}`
    : `服务异常(${resp.status}),请确认后端已启动`
}

/** SSE 消息以空行分隔,格式:data: {...}\n\n */
async function readEventStream(
  body: ReadableStream<Uint8Array>,
  onNode: (node: string, log: string) => void,
): Promise<StreamResult> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  const logs: string[] = []
  let plan: TripPlan | undefined
  let message: string | undefined

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })

    let sep: number
    while ((sep = buf.indexOf('\n\n')) >= 0) {
      const raw = buf.slice(0, sep)
      buf = buf.slice(sep + 2)
      const line = raw.split('\n').find((l) => l.startsWith('data: '))
      if (!line) continue
      const ev = JSON.parse(line.slice(6))
      if (ev.type === 'node') {
        logs.push(ev.log)
        onNode(ev.node, ev.log)
      } else if (ev.type === 'plan') {
        plan = ev.data
      } else if (ev.type === 'error') {
        message = ev.message
      }
    }
  }
  return { ok: !!plan, plan, message, logs }
}
