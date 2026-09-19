"""API 层集成测试:规划成功 → 自动存档 → plan_id 回传 / 历史接口。

整张图与 LLM 全部打桩(参考 smoke_test 的思路),数据库指向 tmp_path 的
临时 SQLite —— 不需要任何 Key、不联网、不碰真实 MySQL。
运行(cd backend):python -m pytest tests/ -v
"""
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api import server as server_module
from app.db import repository
from app.db.database import Base
from app.db.models import TripPlanRecord  # noqa: F401  import 副作用:注册进 Base.metadata
from tests.test_db import make_plan, make_request


@pytest.fixture
def client(tmp_path, monkeypatch):
    """数据库指向临时 SQLite;图打桩成跑两步就出结果"""
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'api_test.db').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    monkeypatch.setattr(
        repository, "SessionLocal", sessionmaker(bind=engine, expire_on_commit=False)
    )
    # lifespan 里的建表改为 no-op,避免测试碰到 .env 指向的真实数据库
    monkeypatch.setattr(server_module, "init_db", lambda: None)

    plan = make_plan()

    async def fake_run_trip(request):
        return {"plan": plan, "log": ["stub"]}

    class FakeGraph:
        """模拟真实图:两个节点各 yield 一次 updates,最后带上 plan"""

        async def astream(self, _input, stream_mode="updates"):
            yield {"weather": {"log": ["🌤 stub"]}}
            yield {"budget": {"plan": plan, "log": ["💰 stub"]}}

    monkeypatch.setattr(server_module, "run_trip", fake_run_trip)
    monkeypatch.setattr(server_module, "trip_graph", FakeGraph())

    with TestClient(server_module.app) as c:
        yield c


class TestAutoArchive:
    def test_plan_endpoint_archives_and_returns_plan_id(self, client):
        body = client.post("/api/plan", json=make_request().model_dump()).json()
        assert body["success"] is True
        assert isinstance(body["plan_id"], int)

        records, total = repository.list_plans()
        assert total == 1
        assert records[0].id == body["plan_id"]
        assert records[0].city == "北京"

    def test_stream_final_event_carries_plan_id(self, client):
        """SSE 最后一条 plan 事件必须带 plan_id,前端靠它知道行程已入库"""
        with client.stream(
            "POST", "/api/plan/stream", json=make_request().model_dump()
        ) as resp:
            chunks = [chunk for chunk in resp.iter_text()]

        events = []
        for line in "".join(chunks).split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))

        assert [e["type"] for e in events] == ["node", "node", "plan"]
        plan_event = events[-1]
        assert isinstance(plan_event["plan_id"], int)
        assert plan_event["data"]["city"] == "北京"

        records, total = repository.list_plans()
        assert total == 1
        assert records[0].id == plan_event["plan_id"]


class TestHistoryEndpoints:
    def test_list_get_delete_roundtrip(self, client):
        pid = repository.save_plan(make_request(), make_plan())

        listed = client.get("/api/plans").json()
        assert listed["success"] is True and listed["total"] == 1
        assert listed["items"][0]["id"] == pid
        assert listed["items"][0]["preferences"] == []  # make_request 无偏好

        detail = client.get(f"/api/plans/{pid}").json()
        assert detail["success"] is True
        assert detail["data"]["city"] == "北京"
        assert detail["request"]["start_date"] == "2026-10-01"

        deleted = client.delete(f"/api/plans/{pid}").json()
        assert deleted["success"] is True
        assert client.get(f"/api/plans/{pid}").json()["success"] is False

    def test_city_filter_and_pagination(self, client):
        from app.models.schemas import TripRequest

        repository.save_plan(make_request(), make_plan("北京"))
        repository.save_plan(
            TripRequest(city="上海市", start_date="2026-10-01", travel_days=3), make_plan("上海市")
        )
        repository.save_plan(make_request(), make_plan("北京"))

        listed = client.get("/api/plans", params={"city": "上海"}).json()
        assert listed["total"] == 1 and listed["items"][0]["city"] == "上海市"

        paged = client.get("/api/plans", params={"limit": 2, "offset": 0}).json()
        assert paged["total"] == 3 and len(paged["items"]) == 2

    def test_missing_plan_is_business_error(self, client):
        """不存在的 id 返回 success=false 的业务响应,而不是 404/500"""
        resp = client.get("/api/plans/999")
        assert resp.status_code == 200
        assert resp.json()["success"] is False
