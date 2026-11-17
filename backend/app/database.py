"""数据库引擎与会话工厂"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,   # 连接取出前先 ping，防 MySQL wait_timeout 断连
    pool_recycle=3600,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：每请求一个会话，结束自动关闭"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
