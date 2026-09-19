"""ORM 模型:成功生成的行程档案

行程结构(Days/Attractions/Meals/...)以 JSON 文本整包存储,不拆成多张表 ——
行程永远整存整取,不存在「按天/按景点查」的需求,拆表只会让 schema
每次演进都变成一场数据迁移。真正要检索/排序的字段(城市、日期、预算)
单独提列出来建索引。
"""
from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class TripPlanRecord(Base):
    __tablename__ = "trip_plans"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    city: Mapped[str] = mapped_column(String(64), index=True)
    start_date: Mapped[str] = mapped_column(String(10))
    end_date: Mapped[str] = mapped_column(String(10))
    travel_days: Mapped[int]
    total_budget: Mapped[int] = mapped_column(default=0, comment="预算总额(元),未生成预算时为 0")
    # 顿号连接的偏好串,列表页直接展示;完整的原始请求另存 request_json
    preferences: Mapped[str] = mapped_column(String(255), default="")
    # JSON 整包存储:MySQL 的 TEXT 只有 64KB,4 天行程的完整 JSON 可能逼近上限,
    # 用 MEDIUMTEXT(16MB);SQLite/PG 上退化为普通 TEXT
    request_json: Mapped[str] = mapped_column(Text().with_variant(MEDIUMTEXT(), "mysql"))
    plan_json: Mapped[str] = mapped_column(Text().with_variant(MEDIUMTEXT(), "mysql"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
