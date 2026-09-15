"""冒烟测试:不联网、不需要任何 API Key,把整张图完整跑一遍。

用法(必须在 backend/ 目录下):
    python smoke_test.py

它验证四件事:
1. `trip_graph` 能编译 —— 依赖版本漂移(例如 requirements 没加上界时被
   解析到 langgraph 1.x)会在这里最先暴露;
2. 三个采集节点并行扇出后,能在 planner 之前正确汇合;
3. planner 返回的天数不对时,条件边会把它送回 planner 重试;
4. budget 节点的预算累加(含住宿夜数)结果正确。

需要一个真实 LLM 或高德 Key 的地方全部打了桩,所以这个脚本可以随时跑。
"""
import asyncio
import sys
import types
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models.schemas import (  # noqa: E402
    Attraction,
    DayPlan,
    Hotel,
    Meal,
    POIInfo,
    TripPlan,
    TripRequest,
    WeatherInfo,
)

START_DATE = "2026-10-01"
TRIP_DAYS = 3

LLM_CALLS = {"n": 0}


# ============ 假 LLM:第一次故意少给一天,用来触发重试环 ============


def _make_plan(days: int) -> TripPlan:
    day_plans = [
        DayPlan(
            date="",
            day_index=i,
            description=f"第{i + 1}天",
            attractions=[Attraction(name="故宫博物院", address="景山前街4号", ticket_price=60)],
            meals=[Meal(type="lunch", name="午饭", estimated_cost=40)],
            hotel=Hotel(name="测试酒店", address="某路1号", estimated_cost=300),
        )
        for i in range(days)
    ]
    return TripPlan(city="北京", start_date="", end_date="", days=day_plans, overall_suggestions="测试")


class _FakeStructured:
    """第 1 次调用返回 2 天(故意不达标),之后返回 3 天。"""

    async def ainvoke(self, prompt: str) -> TripPlan:
        LLM_CALLS["n"] += 1
        days = 2 if LLM_CALLS["n"] == 1 else TRIP_DAYS
        print(f"      [假 LLM] 第 {LLM_CALLS['n']} 次调用 → 返回 {days} 天")
        return _make_plan(days)


class _FakeLLM:
    def with_structured_output(self, *args, **kwargs):
        return _FakeStructured()


def _install_fake_llm() -> None:
    """必须在 import nodes / trip_graph 之前调用。"""
    fake = types.ModuleType("app.services.llm")
    fake.get_llm = lambda *a, **k: _FakeLLM()  # type: ignore[attr-defined]
    sys.modules["app.services.llm"] = fake


# ============ 假高德:覆盖天气与 POI 搜索 ============


async def _fake_get_weather(city: str) -> list[WeatherInfo]:
    """故意多给一天行程范围之外的天气(2026-09-30),验证会被过滤掉。"""
    return [
        WeatherInfo(date="2026-09-30", day_weather="阴", night_weather="阴"),
        WeatherInfo(date="2026-10-01", day_weather="晴", night_weather="多云"),
        WeatherInfo(date="2026-10-02", day_weather="多云", night_weather="晴"),
        WeatherInfo(date="2026-10-03", day_weather="小雨", night_weather="多云"),
    ]


async def _fake_search_poi(keywords: str, city: str, limit: int = 8) -> list[POIInfo]:
    return [
        POIInfo(name=f"{keywords}#{i}", address="测试路", type="风景名胜")
        for i in range(min(limit, 4))
    ]


def _install_fake_amap() -> None:
    from app.services import amap_service

    amap_service.get_weather = _fake_get_weather
    amap_service.search_poi = _fake_search_poi


# ============ 跑 ============


def _print_graph(trip_graph) -> None:
    """打印图拓扑。

    get_graph().draw_ascii() 需要可选的 grandalf 包,没装会抛 ImportError,
    所以这里先试 ASCII 图,不行就退化成「节点 + 边」清单 —— 拓扑信息一样看得到,
    而且不给项目增加一个只为画图存在的依赖。想要 ASCII 图就 pip install grandalf。
    """
    graph = trip_graph.get_graph()
    try:
        print(graph.draw_ascii())
        return
    except ImportError:
        print("   (未安装 grandalf,改用节点/边清单;pip install grandalf 可看 ASCII 图)")

    special = {"__start__", "__end__"}
    print("   节点:", ", ".join(n for n in graph.nodes if n not in special))
    for edge in graph.edges:
        mark = "  [条件边]" if getattr(edge, "conditional", False) else ""
        print(f"     {edge.source} ──► {edge.target}{mark}")


async def run() -> int:
    _install_fake_llm()
    _install_fake_amap()

    try:
        from app.graph.trip_graph import trip_graph
    except ImportError as e:
        print(f"❌ 无法导入 trip_graph:{e}")
        print("   依赖没装好。先执行:pip install -r requirements-dev.txt")
        return 1

    print("① 图编译成功 —— 说明装到的 langgraph 版本与代码兼容")
    _print_graph(trip_graph)

    request = TripRequest(
        city="北京", start_date=START_DATE, travel_days=TRIP_DAYS, preferences=["历史文化", "美食"],
    )

    print("\n② 开始执行(stream_mode=updates)")
    final_plan: TripPlan | None = None
    merged_log: list[str] = []
    async for chunk in trip_graph.astream({"request": request}, stream_mode="updates"):
        for node, update in chunk.items():
            for line in update.get("log", []) or []:
                merged_log.append(line)
                print(f"   ✅ [{node}] {line}")
            if update.get("plan") is not None:
                final_plan = update["plan"]

    print("\n③ 断言")
    failures: list[str] = []

    def check(ok: bool, desc: str) -> None:
        print(f"   {'PASS' if ok else 'FAIL'}  {desc}")
        if not ok:
            failures.append(desc)

    check(final_plan is not None, "图产出了 TripPlan")
    if final_plan is None:
        return 1

    check(len(final_plan.days) == TRIP_DAYS, f"最终行程是 {TRIP_DAYS} 天(实际 {len(final_plan.days)})")
    check(LLM_CALLS["n"] == 2, f"planner 被调用了 2 次,重试环生效(实际 {LLM_CALLS['n']})")
    check(
        [d.day_index for d in final_plan.days] == list(range(TRIP_DAYS)),
        "day_index 被重新编号",
    )
    check(
        [d.date for d in final_plan.days] == ["2026-10-01", "2026-10-02", "2026-10-03"],
        "每天日期被正确回填",
    )
    check(len(final_plan.weather_info) == TRIP_DAYS, f"天气按日期过滤后剩 {TRIP_DAYS} 天(实际 {len(final_plan.weather_info)})")
    check(
        all(w.date != "2026-09-30" for w in final_plan.weather_info),
        "行程范围外的天气(09-30)被过滤掉",
    )
    check(final_plan.budget is not None, "预算已计算")
    if final_plan.budget:
        check(final_plan.budget.nights == TRIP_DAYS - 1, f"住宿 {TRIP_DAYS - 1} 晚(实际 {final_plan.budget.nights})")
        check(final_plan.budget.total_hotels == 300 * (TRIP_DAYS - 1), "住宿总额 = 单晚价 × 晚数")
        check(final_plan.budget.total == final_plan.budget.total_attractions
              + final_plan.budget.total_hotels + final_plan.budget.total_meals, "三项相加等于合计")

    print()
    if failures:
        print(f"❌ 冒烟测试失败:{len(failures)} 项")
        return 1
    print("✅ 冒烟测试全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
