"""FastAPI 服务

两个规划端点:
- POST /api/plan        一次性返回完整结果(简单场景/调试用)
- POST /api/plan/stream SSE 流式:每执行完一个节点就推一条进度事件,

"""
import json
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.models.schemas import TripRequest, TripPlan, TripPlanResponse
from app.graph.trip_graph import run_trip, trip_graph

# 进程入口配置一次日志。没有它,所有 except 都只能把异常变成一句字符串,
# 线上出问题时无从查起。
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
# 注意:root 调到 INFO 之后,httpx 也会以 INFO 打完整请求 URL ——
# 而高德的 API Key 就在 query string 里(key=xxxx),等于把密钥写进日志。
# 这里把 HTTP 客户端的日志压到 WARNING 以上,只保留出错的请求。
for _noisy in ("httpx", "httpcore", "httpx2", "httpcore2"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

app = FastAPI(title="LangGraph 智能旅行助手", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().get_cors_origins_list(),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/plan", response_model=TripPlanResponse)
async def plan_trip(req: TripRequest):
    try:
        state = await run_trip(req)
        plan = state.get("plan")
        if plan is None:
            return TripPlanResponse(success=False, message=state.get("error", "生成失败"))
        return TripPlanResponse(success=True, data=plan, message="\n".join(state.get("log", [])))
    except Exception as e:
        # 堆栈进服务端日志;回给客户端的只是一句通用提示 ——
        # str(e) 里可能带内部 URL(高德 Key 就在 query string 里),不能外泄
        logger.exception("规划失败: %s", e)
        return TripPlanResponse(success=False, message="服务异常,请稍后重试")


@app.post("/api/plan/stream")
async def plan_trip_stream(req: TripRequest):
    """SSE 流式规划:事件格式见前端 src/api.ts 的 planTripStream。"""

    async def event_gen():
        # 边流边合并 state(等价于把 updates 手动 reduce 成最终结果)
        merged: dict = {}
        try:
            async for chunk in trip_graph.astream({"request": req}, stream_mode="updates"):
                for node, upd in chunk.items():
                    for k, v in upd.items():
                        if k == "log":
                            merged.setdefault("log", []).extend(v)
                        else:
                            merged[k] = v
                    log = (upd.get("log") or [""])[0]
                    yield f"data: {json.dumps({'type': 'node', 'node': node, 'log': log}, ensure_ascii=False)}\n\n"

            plan: TripPlan | None = merged.get("plan")
            if plan is None:
                yield f"data: {json.dumps({'type': 'error', 'message': merged.get('error', '生成失败')}, ensure_ascii=False)}\n\n"
            else:
                yield "data: " + json.dumps(
                    {"type": "plan", "data": plan.model_dump(), "log": merged.get("log", [])},
                    ensure_ascii=False,
                ) + "\n\n"
        except Exception as e:
            logger.exception("流式规划失败: %s", e)
            yield f"data: {json.dumps({'type': 'error', 'message': '服务异常,请稍后重试'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# 生产部署:如果前端已 build(npm run build),直接由后端托管静态文件,
# 一个端口同时服务页面和 API。挂载必须放在所有 /api 路由之后。
_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="static")
