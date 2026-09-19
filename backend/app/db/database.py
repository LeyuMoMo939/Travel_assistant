"""数据库连接管理(SQLAlchemy 2.0)

目标后端是 MySQL(连接串在 .env 的 DATABASE_URL),代码层默认回退到
零配置的 SQLite(backend/data/travel.db)—— 没装 MySQL 也能把项目跑起来。
切换 MySQL / PostgreSQL 只改连接串,ORM 模型与仓储代码一行不动
(所以字符串列都显式给了长度:MySQL 建表必须有)。
"""
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, URL, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import BASE_DIR, get_settings


class Base(DeclarativeBase):
    """所有 ORM 模型的公共基类"""


def _resolve_url(url: str) -> str:
    """把相对的 sqlite 路径锚定到 backend/ 目录(理由同 config.py:不能依赖启动目录)。

    否则在仓库根目录启动 uvicorn 时会静默新建另一个空库,
    「历史行程」看起来时有时无,极难排查。Windows 路径的反斜杠
    必须换成 /,否则会被 SQLAlchemy 当成 URL 转义序列。
    """
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return url
    path = url[len(prefix):]
    if not path or path == ":memory:" or path.startswith("/"):
        return url
    p = Path(path)
    if p.is_absolute():
        return url
    return prefix + str((BASE_DIR / p).resolve()).replace("\\", "/")


_engine_url = _resolve_url(get_settings().database_url)

_engine_kwargs: dict = {}
if _engine_url.startswith("sqlite"):
    # FastAPI 把 sync 端点丢进线程池执行,连接会被多个线程轮流使用,
    # SQLite 默认的「同线程检查」必须关掉
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # MySQL/Postgres 的连接闲置久了会被服务端断开,取用前先 ping 一次
    _engine_kwargs["pool_pre_ping"] = True

engine: Engine = create_engine(_engine_url, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def _ensure_mysql_database(url: make_url) -> None:
    """MySQL 不会自动创建数据库:目标库不存在时先建一个。

    用 utf8mb4 建库(兼容中文和 emoji;utf8 在 MySQL 里是残缺的 3 字节实现)。
    若连不上是账号权限/密码/服务没启动的问题,原始异常照常抛出 ——
    那是必须由用户解决的配置问题,静默兜底只会把问题埋进日志深处。
    """
    if not url.database:
        return
    try:
        with engine.connect():
            return  # 库已存在且可正常连接
    except OperationalError as e:
        # 1049 = Unknown database;其他错误码(1045 拒绝访问、2003 连不上)原样抛
        orig_args = getattr(e.orig, "args", None) if e.orig is not None else None
        if not (orig_args and orig_args[0] == 1049):
            raise

    # 注意不能用 url.set(database=None):set() 里传 None 的语义是「保持不变」,
    # 库名根本去不掉(实测就是在这里又抛了 1049)。要用 URL.create 从组件重建。
    server_url = URL.create(
        drivername=url.drivername,
        username=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
    )
    tmp_engine = create_engine(server_url)
    try:
        with tmp_engine.connect() as conn:
            conn.exec_driver_sql(
                f"CREATE DATABASE IF NOT EXISTS `{url.database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            conn.commit()  # DDL 虽是隐式提交,显式 commit 保证各驱动行为一致
    finally:
        tmp_engine.dispose()


def init_db() -> None:
    """建表(幂等,表已存在则跳过)。SQLite 时顺带确保父目录存在。"""
    url = make_url(_engine_url)
    if url.drivername.startswith("sqlite"):
        db_path = _engine_url[len("sqlite:///"):]
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    elif url.drivername.startswith("mysql"):
        _ensure_mysql_database(url)

    from app.db import models  # noqa: F401  import 的副作用是把 ORM 模型注册进 Base.metadata

    Base.metadata.create_all(engine)
