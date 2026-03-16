"""
数据库连接管理 - SQLAlchemy + 连接池
"""
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from sqlalchemy.pool import QueuePool

from app.config import get_settings

settings = get_settings()

# 创建数据库引擎（带连接池）
engine = create_engine(
    settings.DATABASE_URL,
    poolclass=QueuePool,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,  # 自动检测失效连接
    pool_recycle=3600,   # 1小时回收连接
    echo=settings.DEBUG,  # 调试模式下打印SQL
)

# SQLite 特定优化
if settings.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        """设置 SQLite 优化参数"""
        cursor = dbapi_conn.cursor()
        # WAL 模式提升并发性能
        cursor.execute("PRAGMA journal_mode=WAL")
        # 同步模式设为 NORMAL，平衡安全和性能
        cursor.execute("PRAGMA synchronous=NORMAL")
        # 临时表存储在内存中
        cursor.execute("PRAGMA temp_store=MEMORY")
        # 缓存大小设为 100MB
        cursor.execute("PRAGMA cache_size=-100000")
        cursor.close()

# 会话工厂
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False  # 避免提交后对象过期问题
)

# 声明基类
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """获取数据库会话（FastAPI 依赖用）"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """获取数据库会话（上下文管理器，用于后台任务）"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """初始化数据库（创建所有表）"""
    Base.metadata.create_all(bind=engine)
