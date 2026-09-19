"""数据模型:整个项目的数据契约。

自底向上:TripRequest(用户输入) -> TripPlan(最终输出) -> DayPlan(每日) -> Attraction/Meal/Hotel(原子单元)
"""

from datetime import datetime
from typing import List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ============ 用户请求 ============


class TripRequest(BaseModel):
    city: str = Field(..., description="城市名称", examples=["北京"])
    start_date: str = Field(..., description="开始日期 YYYY-MM-DD", examples=["2026-10-01"])
    # 上限 4 天不是产品限制,而是「高德天气预报只有今天起 4 天」:
    # 超过这个窗口的行程仍然能生成,只是不会带天气(见 nodes.planner_node 的日期过滤)
    travel_days: int = Field(..., description="旅行天数", ge=1, le=4)
    transportation: str = Field(default="公共交通", description="交通方式")
    accommodation: str = Field(default="经济型酒店", description="住宿偏好")
    preferences: List[str] = Field(default_factory=list, description="旅行偏好", examples=[["历史文化", "美食"]])
    other_requirements: Optional[str] = Field(default="", description="其他要求")

    @field_validator("start_date")
    @classmethod
    def check_start_date(cls, v: str) -> str:
        """下游 planner_node 会用 %Y-%m-%d 强解日期,格式错必须在这里就拦住,
        否则会在图执行到一半抛 ValueError,前端只能看到一句「服务异常」。"""
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("start_date 必须是 YYYY-MM-DD 格式,例如 2026-10-01")
        return v


# ============ 原子数据单元 ============
#
# 注意:下面三个模型的数据来自高德(外部系统),所以开 extra="forbid"。
# 这样万一字段名写错(例如把 dayweather 写成 dateweather),会当场抛
# ValidationError,而不是被 pydantic 静默忽略、留下一片空白字段。
# 反过来 TripPlan / DayPlan 由 LLM 生成,不要开 forbids,否则模型多返回
# 一个字段就会整体失败。


class Location(BaseModel):
    model_config = ConfigDict(extra="forbid")

    longitude: float = Field(..., description="经度")
    latitude: float = Field(..., description="纬度")


class POIInfo(BaseModel):
    """高德地图搜到的一个兴趣点(景点/酒店通用)"""
    model_config = ConfigDict(extra="forbid")

    name: str
    address: str = ""
    location: Optional[Location] = None
    tel: Optional[str] = None
    type: str = ""


class WeatherInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str = ""
    day_weather: str = ""
    night_weather: str = ""
    day_temp: Union[int, str] = 0
    night_temp: Union[int, str] = 0
    wind_direction: str = ""
    wind_power: str = ""

    @field_validator("day_temp", "night_temp", mode="before")
    @classmethod
    def strip_unit(cls, v):
        """高德返回的温度带 ℃ 单位,统一去掉方便后续计算(注意负数)"""
        if isinstance(v, str):
            v = v.replace("°C", "").replace("℃", "").replace("°", "").strip()
            try:
                return int(v)
            except ValueError:
                return v
        return v


class Attraction(BaseModel):
    name: str = Field(..., description="景点名称")
    address: str = Field(..., description="景点地址")
    location: Optional[Location] = Field(None, description="景点经纬度")
    visit_duration: int = Field(default=120, description="建议游览时间(分钟)")
    description: str = ""
    ticket_price: int = Field(default=0, ge=0, description="门票(元)")


class Meal(BaseModel):
    type: str = Field(..., description="只能是 breakfast / lunch / dinner 三个英文值之一")
    name: str
    description: str = ""
    estimated_cost: int = Field(default=0, ge=0)


class Hotel(BaseModel):
    name: str
    address: str = ""
    estimated_cost: int = Field(default=0, ge=0, description="每晚预估(元)")


class Budget(BaseModel):
    total_attractions: int = 0
    total_hotels: int = 0
    total_meals: int = 0
    total: int = 0
    nights: int = Field(default=0, description="住宿晚数(N 天行程 N-1 晚)")


# ============ 行程(最终输出) ============


class DayPlan(BaseModel):
    date: str
    day_index: int
    description: str = ""
    attractions: List[Attraction] = Field(default_factory=list)
    meals: List[Meal] = Field(default_factory=list)
    hotel: Optional[Hotel] = None


class TripPlan(BaseModel):
    city: str
    start_date: str
    end_date: str
    days: List[DayPlan]
    weather_info: List[WeatherInfo] = Field(default_factory=list)
    overall_suggestions: str = ""
    budget: Optional[Budget] = None


class TripPlanResponse(BaseModel):
    success: bool
    message: str = ""
    data: Optional[TripPlan] = None
    # 成功生成后自动存档得到的记录 id;存档失败或规划失败时为 None
    plan_id: Optional[int] = None


# ============ 历史行程(存档查询) ============


class TripPlanSummary(BaseModel):
    """列表页用的轻量摘要:字段直接取自数据库列,不解析整包 plan_json"""

    id: int
    city: str
    start_date: str
    end_date: str
    travel_days: int
    total_budget: int = 0
    preferences: List[str] = Field(default_factory=list)
    created_at: datetime


class TripPlanListResponse(BaseModel):
    success: bool = True
    message: str = ""
    total: int = 0
    items: List[TripPlanSummary] = Field(default_factory=list)


class TripPlanDetailResponse(BaseModel):
    success: bool = True
    message: str = ""
    data: Optional[TripPlan] = None
    # 当时的原始请求:前端将来可以做「按这套参数重新规划」
    request: Optional[TripRequest] = None
    created_at: Optional[datetime] = None


class TripPlanDeleteResponse(BaseModel):
    success: bool
    message: str = ""
