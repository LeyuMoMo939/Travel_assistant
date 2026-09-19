"""仓储层单测:增删查 / 分页 / 城市过滤 / JSON 无损还原。

用 tmp_path 里的临时 SQLite,不碰真实的数据库(无论它配的是 MySQL 还是 SQLite)。
不需要任何 API Key,也不需要联网。
运行(cd backend):python -m pytest tests/ -v
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import repository
from app.db.database import Base
from app.db.models import TripPlanRecord  # noqa: F401  import 副作用:注册进 Base.metadata
from app.models.schemas import (
    Attraction,
    Budget,
    DayPlan,
    Hotel,
    Meal,
    TripPlan,
    TripRequest,
)


@pytest.fixture
def db(tmp_path, monkeypatch):
    """把 repository 指向临时库,与真实配置完全隔离"""
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    monkeypatch.setattr(repository, "SessionLocal", sessionmaker(bind=engine, expire_on_commit=False))


def make_request(prefs=None) -> TripRequest:
    return TripRequest(city="北京", start_date="2026-10-01", travel_days=3, preferences=prefs or [])


def make_plan(city: str = "北京") -> TripPlan:
    days = [
        DayPlan(
            date=f"2026-10-0{i + 1}",
            day_index=i,
            attractions=[Attraction(name=f"景点{i}", address="某路", ticket_price=50)],
            meals=[Meal(type="lunch", name="午饭", estimated_cost=30)],
            hotel=Hotel(name="测试酒店", estimated_cost=300),
        )
        for i in range(3)
    ]
    plan = TripPlan(city=city, start_date="2026-10-01", end_date="2026-10-03", days=days)
    plan.budget = Budget(total_attractions=150, total_hotels=600, total_meals=90, total=840, nights=2)
    return plan


class TestSaveAndGet:
    def test_roundtrip_without_loss(self, db):
        """存进去再读出来:结构化字段和整包 JSON 都必须无损还原"""
        req, plan = make_request(["美食", "历史文化"]), make_plan()
        plan_id = repository.save_plan(req, plan)

        record = repository.get_plan(plan_id)
        assert record is not None
        assert record.city == "北京"
        assert record.travel_days == 3
        assert record.total_budget == 840
        assert record.preferences == "美食、历史文化"
        assert TripPlan.model_validate_json(record.plan_json) == plan
        assert TripRequest.model_validate_json(record.request_json) == req

    def test_ids_increase(self, db):
        first = repository.save_plan(make_request(), make_plan())
        second = repository.save_plan(make_request(), make_plan())
        assert second > first

    def test_get_missing_returns_none(self, db):
        assert repository.get_plan(999) is None


class TestList:
    def test_orders_by_created_desc(self, db):
        for _ in range(3):
            repository.save_plan(make_request(), make_plan())
        records, total = repository.list_plans()
        assert total == 3
        assert [r.id for r in records] == sorted([r.id for r in records], reverse=True)

    def test_city_filter_is_fuzzy(self, db):
        # 存档的 city 取自 plan.city(LLM 生成行程的归属城市),测试要两边一致
        repository.save_plan(TripRequest(city="北京", start_date="2026-10-01", travel_days=2), make_plan("北京"))
        repository.save_plan(TripRequest(city="上海市", start_date="2026-10-01", travel_days=2), make_plan("上海市"))

        _, total_sh = repository.list_plans(city="上海")  # 「上海」能匹配到「上海市」
        assert total_sh == 1
        _, total_bj = repository.list_plans(city="北京")
        assert total_bj == 1
        _, total_all = repository.list_plans()
        assert total_all == 2

    def test_pagination(self, db):
        for _ in range(3):
            repository.save_plan(make_request(), make_plan())
        page1, total = repository.list_plans(limit=2, offset=0)
        page2, _ = repository.list_plans(limit=2, offset=2)
        assert total == 3
        assert len(page1) == 2 and len(page2) == 1
        assert {r.id for r in page1} & {r.id for r in page2} == set()  # 两页不重叠


class TestDelete:
    def test_delete_existing(self, db):
        plan_id = repository.save_plan(make_request(), make_plan())
        assert repository.delete_plan(plan_id) is True
        assert repository.get_plan(plan_id) is None

    def test_delete_missing_is_false(self, db):
        assert repository.delete_plan(999) is False
