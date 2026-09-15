"""图的节点函数

约定:节点返回一个 dict,只包含要更新的键;LangGraph 负责把它合并进 state。
三个采集节点(weather / attractions / hotels)互不依赖,在图里会被并行调度。

容错原则:采集节点各自 try/except,失败时返回空数据 + 警告日志,
同时把完整堆栈写进服务端日志 —— 否则「失败降级」和「真的没数据」在
外面看起来一模一样,问题会无限期潜伏。
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta

from app.models.schemas import Budget, Hotel, TripPlan, TripRequest
from app.services import amap_service
from app.services.llm import get_llm

logger = logging.getLogger(__name__)

MAX_PLANNER_ATTEMPTS = 2  # 校验不通过时最多重新生成次数(总共尝试 2 次)
MAX_ATTRACTION_PREFERENCES = 3  # 最多合并几个偏好去搜景点,控制请求数与候选规模


# ============ 采集节点(并行执行) ============


async def weather_node(state: dict) -> dict:
    """查询目的地未来几天天气"""
    city = state["request"].city
    try:
        weather = await amap_service.get_weather(city)
        log = f"🌤 天气查询完成:{city} 共{len(weather)}天数据"
    except Exception as e:
        logger.warning("天气查询失败 city=%s: %s", city, e, exc_info=True)
        weather = []
        log = f"⚠️ 天气查询失败({e}),行程将不带天气参考"
    return {"weather": weather, "log": [log]}


async def attraction_node(state: dict) -> dict:
    """按用户偏好搜索景点:多个偏好并行检索后合并去重

    只取 preferences[0] 会浪费掉用户的其他选择,所以这里把前几个偏好都发出去。
    单个偏好失败不影响其他偏好(return_exceptions=True),全部失败才降级。
    """
    request = state["request"]
    prefs = (request.preferences or ["景点"])[:MAX_ATTRACTION_PREFERENCES]
    try:
        batches = await asyncio.gather(
            *(amap_service.search_poi(f"{p}景点", request.city, limit=6) for p in prefs),
            return_exceptions=True,
        )

        pois: list = []
        seen: set = set()
        failed: list = []
        for pref, batch in zip(prefs, batches):
            if isinstance(batch, BaseException):
                failed.append(pref)
                logger.warning("景点检索失败 pref=%s: %s", pref, batch, exc_info=batch)
                continue
            for p in batch:
                if p.name and p.name not in seen:
                    seen.add(p.name)
                    pois.append(p)

        if len(failed) == len(prefs):
            raise RuntimeError(f"{len(prefs)} 个偏好检索全部失败:{failed[0]}")

        pois = pois[:10]  # 控制喂给 LLM 的候选规模
        if not pois:  # 一个有名字的都没搜到:退化成泛化关键词再试一次
            pois = await amap_service.search_poi("景点", request.city, limit=8)

        log = f"📍 景点搜索完成:合并{len(prefs)}个偏好,共{len(pois)}个候选"
    except Exception as e:
        logger.warning("景点搜索失败 city=%s: %s", request.city, e, exc_info=True)
        pois = []
        log = f"⚠️ 景点搜索失败({e}),行程将由 LLM 基于常识生成"
    return {"attractions": pois, "log": [log]}


# 不同住宿档位的每晚预估价(高德 POI 不带房价,这里按档位给经验估算值)
PRICE_BY_ACCOMMODATION = {
    "经济型酒店": 300,
    "舒适型酒店": 500,
    "豪华型酒店": 900,
    "民宿": 250,
}


async def hotel_node(state: dict) -> dict:
    """搜索酒店候选,价格按档位估算

    注意:高德 POI 的名称里不会出现「经济型酒店」这种档位词,拿它当关键词
    基本搜不到东西。所以统一搜「酒店」,档位只用来决定预估房价。
    """
    request = state["request"]
    try:
        pois = await amap_service.search_poi("酒店", request.city, limit=8)
        estimated = PRICE_BY_ACCOMMODATION.get(request.accommodation, 350)
        hotels = [
            Hotel(name=p.name, address=p.address, estimated_cost=estimated)
            for p in pois
        ]
        log = f"🏨 酒店搜索完成:找到{len(hotels)}家候选(按「{request.accommodation}」估{estimated}元/晚)"
    except Exception as e:
        logger.warning("酒店搜索失败 city=%s: %s", request.city, e, exc_info=True)
        hotels = []
        log = f"⚠️ 酒店搜索失败({e}),行程将不推荐具体酒店"
    return {"hotels": hotels, "log": [log]}


# ============ 规划节点(LLM 结构化输出) ============


PLANNER_PROMPT = """你是资深旅行规划师。请根据下面给出的真实数据,生成一份{days}天的旅行计划。

【目的地】{city}
【日期】{start_date} 起 {days} 天
【交通方式】{transportation}
【住宿偏好】{accommodation}
【用户偏好】{preferences}
【额外要求】{free_text}

【候选景点(高德地图真实数据)】
{attractions}

【候选酒店】
{hotels}

【天气预报】
{weather}

要求:
1. 每天安排 2-3 个景点,注意景点之间的地理位置,同一天的景点尽量就近
2. 雨天/极端天气当天优先安排室内活动;若【天气预报】为空,不要臆测天气
3. 每天必须包含早餐、午餐、晚餐推荐(含预估费用)
4. 每天从候选酒店中选一家
5. overall_suggestions 给出实用的综合建议
6. days 数组必须恰好包含 {days} 个元素,一天都不能多、不能少
7. meals 每一项的 type 字段只能填这三个英文值之一:breakfast / lunch / dinner
"""


async def planner_node(state: dict) -> dict:
    """调用 LLM,把采集到的真实数据整合成结构化的 TripPlan。

    若 validate 节点发现天数不符,图会路由回本节点重试,
    state 里的 planner_feedback 会附在 prompt 末尾帮模型纠正。
    """

    request: TripRequest = state["request"]
    attempts = state.get("planner_attempts", 0) + 1

    start = datetime.strptime(request.start_date, "%Y-%m-%d")
    end = start + timedelta(days=request.travel_days - 1)

    # 高德天气预报只有「今天起 4 天」。必须按日期对齐,不能按顺序硬截:
    # 出行日期落在预报窗口外时,宁可不给天气,也不能把出行前一周的天气
    # 当成行程天气既喂给 LLM、又展示给用户。
    trip_dates = {
        (start + timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(request.travel_days)
    }
    weather = [w for w in state.get("weather", []) if w.date in trip_dates]

    prompt = PLANNER_PROMPT.format(
        days=request.travel_days,
        city=request.city,
        start_date=request.start_date,
        transportation=request.transportation,
        accommodation=request.accommodation,
        preferences="、".join(request.preferences) or "无",
        free_text=request.other_requirements or "无",
        attractions=json.dumps(
            [p.model_dump(exclude_none=True) for p in state.get("attractions", [])],
            ensure_ascii=False, indent=1,
        ),
        hotels=json.dumps(
            [h.model_dump(exclude_none=True) for h in state.get("hotels", [])],
            ensure_ascii=False, indent=1,
        ),
        weather=json.dumps(
            [w.model_dump(exclude_none=True) for w in weather],
            ensure_ascii=False, indent=1,
        ),
    )

    feedback = state.get("planner_feedback")
    if feedback:
        prompt += f"\n\n【上一次生成的问题,必须纠正】\n{feedback}"

    # 结构化输出:让模型直接产出符合 TripPlan schema 的 JSON,免手写解析。
    # method="function_calling":部分模型(如 deepseek-v4-pro)不支持
    # 默认的 json_schema 响应格式,但都支持通过工具调用来约束输出结构。
    llm = get_llm().with_structured_output(TripPlan, method="function_calling")
    plan: TripPlan = await llm.ainvoke(prompt)

    # 补齐 LLM 容易写错/漏写的字段
    plan.start_date = request.start_date
    plan.end_date = end.strftime("%Y-%m-%d")
    plan.weather_info = weather
    for i, day in enumerate(plan.days):
        day.day_index = i
        day.date = (start + timedelta(days=i)).strftime("%Y-%m-%d")

    return {
        "plan": plan,
        "planner_attempts": attempts,
        "planner_feedback": None,  # 清除上次的反馈
        "log": [
            f"📋 第{attempts}次生成完成:共{len(plan.days)}天"
            + (f",天气{len(weather)}天" if weather else "(无可用天气:出行日期超出预报窗口)")
        ],
    }


# ============ 校验节点(重试环的裁判) ============


def validate_node(state: dict) -> dict:
    """检查行程天数是否达标;把结论写进 plan_ok,作为唯一的判断依据

    判断只在这里做一次,条件边直接读 plan_ok —— 避免节点和路由各算一遍
    导致两边结论不一致。
    """
    plan: TripPlan | None = state.get("plan")
    request = state["request"]
    n = len(plan.days) if plan else 0

    if n == request.travel_days:
        return {"plan_ok": True, "log": ["✅ 行程校验通过"]}

    logger.warning("行程天数校验未通过: %s/%s", n, request.travel_days)
    return {
        "plan_ok": False,
        "planner_feedback": (
            f"用户要求 {request.travel_days} 天行程,你上次生成了 {n} 天。"
            f"days 数组长度必须恰好等于 {request.travel_days}。"
        ),
        "log": [f"⚠️ 行程校验未通过({n}/{request.travel_days}天)"],
    }


def route_after_validate(state: dict) -> str:
    """条件边:合格 → budget;不合格且还有重试机会 → planner;否则放行"""
    if state.get("plan_ok"):
        return "budget"
    if state.get("planner_attempts", 0) < MAX_PLANNER_ATTEMPTS:
        return "planner"
    logger.warning("重试用尽仍不合格,放行(行程天数可能与请求不符)")
    return "budget"


# ============ 收尾节点 ============


def budget_node(state: dict) -> dict:
    """预算确定性累加"""
    plan: TripPlan = state.get("plan")
    if plan is None:
        return {"error": "行程生成失败,无法计算预算",
                "log": ["❌ 流程结束:未生成行程"]}

    total_attractions = sum(a.ticket_price for d in plan.days for a in d.attractions)
    total_meal = sum(m.estimated_cost for d in plan.days for m in d.meals)

    # N 天行程住 N-1 晚(当天往返算 0 晚)。所有天用同一档位价,取第一家有报价的。
    nights = max(len(plan.days) - 1, 0)
    nightly = next((d.hotel.estimated_cost for d in plan.days if d.hotel), 0)
    total_hotel = nightly * nights

    plan.budget = Budget(
        total_attractions=total_attractions,
        total_hotels=total_hotel,
        total_meals=total_meal,
        total=total_attractions + total_hotel + total_meal,
        nights=nights,
    )
    return {"plan": plan,
            "log": [f"💰 预算计算完成:住宿{nights}晚,总计 {plan.budget.total} 元"]}
