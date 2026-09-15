"""节点纯逻辑单测:预算 / 温度清洗 / 日期校验 / 重试路由。

不需要任何 API Key,也不需要联网。
运行(cd backend):python -m pytest tests/ -v
"""
import pytest

from app.graph.nodes import (
    MAX_PLANNER_ATTEMPTS,
    budget_node,
    route_after_validate,
    validate_node,
)
from app.models.schemas import (
    Attraction,
    DayPlan,
    Hotel,
    Meal,
    TripPlan,
    TripRequest,
    WeatherInfo,
)


def make_request(days: int = 3) -> TripRequest:
    return TripRequest(city="北京", start_date="2026-10-01", travel_days=days)


def make_plan(days: int = 3, nightly: int = 300) -> TripPlan:
    day_plans = [
        DayPlan(
            date=f"2026-10-0{i + 1}",
            day_index=i,
            attractions=[Attraction(name=f"景点{i}", address="某路", ticket_price=50)],
            meals=[Meal(type="lunch", name="午饭", estimated_cost=30)],
            hotel=Hotel(name="测试酒店", estimated_cost=nightly),
        )
        for i in range(days)
    ]
    return TripPlan(city="北京", start_date="2026-10-01", end_date="2026-10-03", days=day_plans)


class TestBudget:
    def test_nights_is_days_minus_one(self):
        """3 天行程住 2 晚 —— 曾经按天数累加,住宿费系统性偏高。"""
        state = budget_node({"request": make_request(3), "plan": make_plan(3, nightly=300)})
        budget = state["plan"].budget
        assert budget.nights == 2
        assert budget.total_hotels == 600

    def test_single_day_trip_has_no_hotel_cost(self):
        state = budget_node({"request": make_request(1), "plan": make_plan(1)})
        budget = state["plan"].budget
        assert budget.nights == 0
        assert budget.total_hotels == 0

    def test_totals_add_up(self):
        budget = budget_node({"request": make_request(3), "plan": make_plan(3)})["plan"].budget
        assert budget.total == (
            budget.total_attractions + budget.total_hotels + budget.total_meals
        )

    def test_plan_without_hotel_is_tolerated(self):
        plan = make_plan(3)
        for day in plan.days:
            day.hotel = None
        budget = budget_node({"request": make_request(3), "plan": plan})["plan"].budget
        assert budget.total_hotels == 0

    def test_missing_plan_returns_error(self):
        assert "error" in budget_node({"request": make_request(3)})


class TestValidateAndRouting:
    def test_matching_days_passes(self):
        state = validate_node({"request": make_request(3), "plan": make_plan(3)})
        assert state["plan_ok"] is True

    def test_wrong_days_fails_with_feedback(self):
        state = validate_node({"request": make_request(3), "plan": make_plan(2)})
        assert state["plan_ok"] is False
        assert "3" in state["planner_feedback"]

    def test_route_goes_to_budget_when_ok(self):
        assert route_after_validate({"plan_ok": True}) == "budget"

    def test_route_retries_while_attempts_left(self):
        assert route_after_validate({"plan_ok": False, "planner_attempts": 1}) == "planner"

    def test_route_gives_up_after_max_attempts(self):
        state = {"plan_ok": False, "planner_attempts": MAX_PLANNER_ATTEMPTS}
        assert route_after_validate(state) == "budget"


class TestWeatherInfo:
    def test_temperature_unit_is_stripped(self):
        w = WeatherInfo(date="2026-10-01", day_temp="24℃", night_temp="-3°C")
        assert w.day_temp == 24
        assert w.night_temp == -3

    def test_wrong_field_name_is_rejected(self):
        """字段名写错必须当场报错。

        高德预报接口的字段是 dayweather,曾经被写成 dateweather —— 因为
        pydantic 默认忽略未知字段,白天天气一直是空字符串却没人发现。
        """
        with pytest.raises(Exception):
            WeatherInfo(date="2026-10-01", date_weather="晴")


class TestTripRequestValidation:
    def test_bad_date_format_is_rejected(self):
        with pytest.raises(Exception):
            TripRequest(city="北京", start_date="2026/10/01", travel_days=3)

    def test_good_date_is_accepted(self):
        req = TripRequest(city="北京", start_date="2026-10-01", travel_days=3)
        assert req.start_date == "2026-10-01"

    def test_days_out_of_range_is_rejected(self):
        with pytest.raises(Exception):
            TripRequest(city="北京", start_date="2026-10-01", travel_days=5)
