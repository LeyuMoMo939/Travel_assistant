"""仓储层:行程档案的增删查。

每个函数自开自管 Session(短事务,用完即还)。注意 save_plan 会把
数据库异常原样抛出 —— 是否容忍由调用方决定:服务端只记日志、不中断
正在返回的规划结果,单测/脚本则可以直接看到失败。
"""
import logging
from typing import List, Optional, Tuple

from sqlalchemy import func, select

from app.db.database import SessionLocal
from app.db.models import TripPlanRecord
from app.models.schemas import TripPlan, TripRequest

logger = logging.getLogger(__name__)


def save_plan(request: TripRequest, plan: TripPlan) -> int:
    """存一份成功生成的行程,返回自增 id"""
    record = TripPlanRecord(
        city=plan.city,
        start_date=plan.start_date,
        end_date=plan.end_date,
        travel_days=len(plan.days),
        total_budget=plan.budget.total if plan.budget else 0,
        preferences="、".join(request.preferences)[:255],
        request_json=request.model_dump_json(),
        plan_json=plan.model_dump_json(),
    )
    with SessionLocal() as session:
        session.add(record)
        session.commit()
        return record.id


def list_plans(
    limit: int = 20, offset: int = 0, city: Optional[str] = None
) -> Tuple[List[TripPlanRecord], int]:
    """分页列出记录(按保存时间倒序),返回 (记录列表, 过滤后的总数)。

    返回 ORM 记录而不是 DTO:列表页只需要提列字段,不值得把整包
    plan_json 反序列化一遍。city 做模糊匹配,兼容「北京/北京市」。
    """
    with SessionLocal() as session:
        stmt = select(TripPlanRecord)
        count_stmt = select(func.count(TripPlanRecord.id))
        if city:
            stmt = stmt.where(TripPlanRecord.city.contains(city))
            count_stmt = count_stmt.where(TripPlanRecord.city.contains(city))
        total = session.scalar(count_stmt) or 0
        records = session.scalars(
            stmt.order_by(TripPlanRecord.created_at.desc(), TripPlanRecord.id.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        return list(records), total


def get_plan(plan_id: int) -> Optional[TripPlanRecord]:
    with SessionLocal() as session:
        return session.get(TripPlanRecord, plan_id)


def delete_plan(plan_id: int) -> bool:
    """删除一条记录;返回「是否真的删了」(不存在返回 False,由调用方定语义)"""
    with SessionLocal() as session:
        record = session.get(TripPlanRecord, plan_id)
        if record is None:
            return False
        session.delete(record)
        session.commit()
        return True
