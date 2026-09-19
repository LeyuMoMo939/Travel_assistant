"""命令行入口(CLI)示例

不带参数则使用默认值。演示了 LangGraph 的流式输出:
每执行完一个节点,就能立刻看到它的更新。

注意:整张图只跑一次!用 astream 同时订阅 updates(节点增量)和
values(全量 state)两种模式,拿最后一次 values 当最终结果,
绝不能 astream 完再 ainvoke —— 那会把整张图(包括 LLM 调用)跑两遍。
"""
import argparse
import asyncio

from app.models.schemas import TripRequest
from app.graph.trip_graph import trip_graph
from app.db import repository
from app.db.database import init_db


def parse_args() -> argparse.Namespace:
    """用 argparse,而不是手撸 sys.argv。

    手撸的写法只过滤掉 --preferences 这个 flag、没过滤它的值,于是
    `main.py 北京 --preferences 美食` 会把「美食」当成 start_date。
    """
    parser = argparse.ArgumentParser(
        description="智能旅行助手 CLI",
        epilog="示例:python main.py 北京 2026-10-01 3 --preferences 历史文化 美食",
    )
    parser.add_argument("city", nargs="?", default="北京", help="目的地城市(默认:北京)")
    parser.add_argument("start_date", nargs="?", default="2026-10-01", help="出发日期 YYYY-MM-DD")
    parser.add_argument("travel_days", nargs="?", type=int, default=3, help="旅行天数 1-4")
    # nargs="*" 会把后面的裸词全吃掉,所以 --preferences 必须放在最后
    parser.add_argument("--preferences", nargs="*", default=[], help="旅行偏好,空格分隔(放最后)")
    return parser.parse_args()


async def main():
    ns = parse_args()
    city, start_date, travel_days = ns.city, ns.start_date, ns.travel_days
    preferences = ns.preferences

    request = TripRequest(
        city=city,
        start_date=start_date,
        travel_days=travel_days,
        preferences=preferences,
    )
    print(f"🚀 开始规划:{city} {start_date} 起 {travel_days} 天,偏好: {preferences or '无'}\n")

    # 一次流式执行,同时拿到「节点进度」和「最终 state」
    final_state: dict = {}
    async for mode, chunk in trip_graph.astream(
        {"request": request}, stream_mode=["updates", "values"]
    ):
        if mode == "updates":
            for node_name, update in chunk.items():
                log = update.get("log", [""])
                print(f"✅ [{node_name}] {log[0] if log else 'done'}")
        else:  # values:每个超步结束后的全量 state,最后一个就是最终结果
            final_state = chunk

    plan = final_state.get("plan")
    if plan is None:
        print(f"\n❌ 失败:{final_state.get('error')}")
        return

    print("\n" + "=" * 60)
    print(f"📍 {plan.city} {plan.start_date} ~ {plan.end_date}")
    print(f"💡 {plan.overall_suggestions}")
    for day in plan.days:
        print(f"\n--- 第{day.day_index + 1}天 {day.date} | {day.description} ---")
        for a in day.attractions:
            print(f"  🏛 {a.name}({a.address}) 门票:{a.ticket_price}元 建议游览{a.visit_duration}分钟")
        for m in day.meals:
            print(f"  🍜 [{m.type}] {m.name} 约{m.estimated_cost}元")
        if day.hotel:
            print(f"  🏨 {day.hotel.name} 约{day.hotel.estimated_cost}元/晚")
    if plan.budget:
        print(f"\n💰 预算:门票{plan.budget.total_attractions} + 住宿{plan.budget.total_hotels}"
              f"({plan.budget.nights}晚) + 餐饮{plan.budget.total_meals} = 总计 {plan.budget.total} 元")

    # 与 API 行为一致:成功的行程自动存档。CLI 里存档失败只提示,不影响查看结果
    try:
        init_db()
        plan_id = repository.save_plan(request, plan)
        print(f"\n🗄 行程已存档(#{plan_id}),可在前端「历史行程」里回看")
    except Exception as e:
        print(f"\n⚠️ 行程存档失败(不影响本次结果):{e}")


if __name__ == "__main__":
    asyncio.run(main())
