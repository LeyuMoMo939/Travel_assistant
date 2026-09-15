"""组装 LangGraph 工作流。

图的拓扑:

              ┌──────────────┐
      ┌──────►│ weather_node │──────┐
      │       └──────────────┘      │
 START─┼──────►│ attraction_node│─────┼──► planner ──► validate ─┬─(合格/重试用尽)─► budget ──► END
      │       └──────────────┘      │                    ▲     │
      └──────►│  hotel_node    │─────┘                    │   (不合格且还有机会)
              └──────────────┘                       └────┘ 条件边回 planner 重试

- 三个采集节点从 START 并行扇出(fan-out),在 planner 前汇合(fan-in),
  LangGraph 会自动等三条分支全部完成才继续(同步语义)。
- validate 节点检查行程天数;不合格时由条件边(add_conditional_edges)
  把图路由回 planner 重试,最多 MAX_PLANNER_ATTEMPTS 次。
"""

from langgraph.graph import StateGraph, START, END

from app.graph.state import TripState
from app.graph.nodes import (
    weather_node, attraction_node, hotel_node,
    planner_node, validate_node, route_after_validate, budget_node,
)


def build_trip_graph():
    builder = StateGraph(TripState)

    # 注册节点:名字 -> 函数
    builder.add_node("weather", weather_node)
    builder.add_node("attractions", attraction_node)
    builder.add_node("hotels", hotel_node)
    builder.add_node("planner", planner_node)
    builder.add_node("validate", validate_node)
    builder.add_node("budget", budget_node)

    # 并行扇出:START 同时连三个采集节点
    builder.add_edge(START, "weather")
    builder.add_edge(START, "attractions")
    builder.add_edge(START, "hotels")

    # 汇合:三个采集节点都指向 planner
    builder.add_edge(["weather", "attractions", "hotels"], "planner")

    # 规划 → 校验 → 条件边决定放行或重试
    builder.add_edge("planner", "validate")
    builder.add_conditional_edges(
        "validate",
        route_after_validate,
        {"planner": "planner", "budget": "budget"},
    )

    builder.add_edge("budget", END)
    return builder.compile()


# 模块级单例,import 时即编译好
trip_graph = build_trip_graph()


async def run_trip(request) -> dict:
    """便捷入口:跑完整个图,返回最终 state"""
    return await trip_graph.ainvoke({"request": request})
