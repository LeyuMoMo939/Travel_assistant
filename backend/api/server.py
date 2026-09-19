"""FastAPI 服务

规划端点:
- POST /api/plan        一次性返回完整结果(简单场景/调试用)
- POST /api/plan/stream SSE 流式:每执行完一个节点就推一条进度事件,

历史行程端点(数据库存档,见 app/db/):
- GET    /api/plans         列表(分页 + 城市过滤)
- GET    /api/plans/{id}    详情(完整 TripPlan)
- DELETE /api/plans/{id}    删除
"""
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db import repository
from app.db.database import init_db
from app.models.schemas import (
    TripPlanListResponse,
    TripPlan,
    TripPlanDeleteResponse,
    TripPlanDetailResponse,
    TripPlanSummary,
    TripRequest,
    TripPlanResponse,
)
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

@asynccontextmanager
async def lifespan(_: FastAPI):
    # 建表放启动时而不是 import 时:幂等、只跑一次,失败也能在日志里一眼看到。
    # 建表失败只降级(规划照常,历史功能不可用),不该让整个服务起不来。
    try:
        await asyncio.to_thread(init_db)
    except Exception as e:
        logger.exception("数据库初始化失败,历史行程功能不可用(规划不受影响): %s", e)
    yield


app = FastAPI(title="LangGraph 智能旅行助手", version="1.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().get_cors_origins_list(),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


async def _save_plan(req: TripRequest, plan: TripPlan) -> int | None:
    """规划成功后自动存档,返回记录 id。

    存档是「附赠功能」,失败只记日志 —— 绝不能让保存这个附带动作
    毁掉一次已经成功的规划(比如 MySQL 没启动时,行程照样能正常返回)。
    """
    try:
        return await asyncio.to_thread(repository.save_plan, req, plan)
    except Exception as e:
        logger.exception("行程存档失败(不影响本次规划): %s", e)
        return None


@app.post("/api/plan", response_model=TripPlanResponse)
async def plan_trip(req: TripRequest):
    try:
        state = await run_trip(req)
        plan = state.get("plan")
        if plan is None:
            return TripPlanResponse(success=False, message=state.get("error", "生成失败"))
        plan_id = await _save_plan(req, plan)
        return TripPlanResponse(
            success=True, data=plan, message="\n".join(state.get("log", [])), plan_id=plan_id
        )
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
                # 存完再发最终事件:前端能拿到 plan_id,知道这条行程已入库
                plan_id = await _save_plan(req, plan)
                yield "data: " + json.dumps(
                    {
                        "type": "plan",
                        "data": plan.model_dump(),
                        "log": merged.get("log", []),
                        "plan_id": plan_id,
                    },
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


# ============ 历史行程(数据库存档的增删查) ============
#
# 端点用 sync def:FastAPI 会自动丢进线程池,不会阻塞事件循环;
# 查询失败降级成 success=false 的业务响应,与 /api/plan 的风格一致。


@app.get("/api/plans", response_model=TripPlanListResponse)
def list_history_plans(
    limit: int = Query(20, ge=1, le=100, description="每页条数"),
    offset: int = Query(0, ge=0, description="跳过条数"),
    city: str | None = Query(None, description="按城市过滤(模糊匹配)"),
):
    """历史行程列表:轻量摘要(不含完整行程),按保存时间倒序。"""
    try:
        records, total = repository.list_plans(limit=limit, offset=offset, city=city)
    except Exception as e:
        logger.exception("历史行程查询失败: %s", e)
        return TripPlanListResponse(success=False, message="历史行程查询失败,请确认数据库配置正确且已启动")
    items = [
        TripPlanSummary(
            id=r.id,
            city=r.city,
            start_date=r.start_date,
            end_date=r.end_date,
            travel_days=r.travel_days,
            total_budget=r.total_budget,
            preferences=r.preferences.split("、") if r.preferences else [],
            created_at=r.created_at,
        )
        for r in records
    ]
    return TripPlanListResponse(total=total, items=items)


@app.get("/api/plans/{plan_id}", response_model=TripPlanDetailResponse)
def get_history_plan(plan_id: int):
    """单条历史行程:完整 TripPlan,顺带返回当时的原始请求(便于「按这套参数重新规划」)。"""
    try:
        record = repository.get_plan(plan_id)
    except Exception as e:
        logger.exception("历史行程查询失败 id=%s: %s", plan_id, e)
        return TripPlanDetailResponse(success=False, message="历史行程查询失败,请确认数据库配置正确且已启动")
    if record is None:
        return TripPlanDetailResponse(success=False, message=f"行程 #{plan_id} 不存在")
    # plan_json 是历史数据:schema 演进后旧记录可能解析失败,兜底成业务错误而不是 500
    try:
        plan = TripPlan.model_validate_json(record.plan_json)
    except Exception as e:
        logger.exception("历史行程解析失败 id=%s: %s", plan_id, e)
        return TripPlanDetailResponse(success=False, message="该行程由旧版本生成,数据格式已不兼容")
    detail = TripPlanDetailResponse(success=True, data=plan, created_at=record.created_at)
    try:
        detail.request = TripRequest.model_validate_json(record.request_json)
    except Exception:
        detail.request = None  # 原始请求解析失败不影响主数据
    return detail


@app.delete("/api/plans/{plan_id}", response_model=TripPlanDeleteResponse)
def delete_history_plan(plan_id: int):
    try:
        removed = repository.delete_plan(plan_id)
    except Exception as e:
        logger.exception("历史行程删除失败 id=%s: %s", plan_id, e)
        return TripPlanDeleteResponse(success=False, message="删除失败,请稍后重试")
    if not removed:
        return TripPlanDeleteResponse(success=False, message=f"行程 #{plan_id} 不存在")
    return TripPlanDeleteResponse(success=True, message="已删除")


# 生产部署:如果前端已 build(npm run build),直接由后端托管静态文件,
# 一个端口同时服务页面和 API。挂载必须放在所有 /api 路由之后。
_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="static")
