"""图的 State 定义
关键点:
1. State 是节点之间传递的唯一载体,每个节点读 state、返回增量更新。
2. log 字段用了 Annotated + operator.add reducer:多个并行节点同时往里
   追加日志时,LangGraph 自动合并而不是互相覆盖 —— 这是并行扇出的关键。
3. total=False 让所有键可选,方便部分更新。
"""
import operator
from typing import Annotated, List, Optional
from typing_extensions import TypedDict

from app.models.schemas import TripRequest, TripPlan, POIInfo, WeatherInfo, Hotel

class TripState(TypedDict, total=False):
    """旅行规划的状态"""

    # 用户请求
    request: TripRequest

    # 并行节点各自写入的数据
    weather: List[WeatherInfo]
    attractions: List[POIInfo]
    hotels: List[Hotel]

    # 规划师输出
    plan: Optional[TripPlan]
    error: Optional[str]

    # 校验-重试环:validate 节点发现天数不符时写 feedback,并把图路由回 planner
    planner_attempts: int        # planner 已执行的次数
    planner_feedback: Optional[str]  # 给规划师的上次失败反馈
    plan_ok: bool                # validate 的唯一结论,条件边据此路由(避免两处各算一遍)

    # 执行日志(每个节点追加一行,reducer 自动合并)
    log: Annotated[List[str], operator.add]
