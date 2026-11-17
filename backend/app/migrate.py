"""应用启动时执行 Alembic 迁移（AUTO_MIGRATE=true 时）。

- 先用 MySQL GET_LOCK 防止多实例并发迁移
- 优先使用独立 MIGRATE_DATABASE_URL，避免复用无 DDL 权限的主应用连接池
- 迁移失败直接抛异常，让容器启动失败，避免“代码上了、库没迁”
- AUTO_MIGRATE 默认关闭，由部署环境显式打开
"""

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

import app.database as app_db
from app.config import settings

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[1]
LOCK_NAME = "hr_migrate"


def run_migrations() -> None:
    if not settings.AUTO_MIGRATE:
        return

    migrate_url = settings.resolve_migrate_database_url()
    using_dedicated_engine = bool(settings.MIGRATE_DATABASE_URL.strip())
    target_engine = (
        create_engine(migrate_url, pool_pre_ping=True)
        if using_dedicated_engine
        else app_db.engine
    )

    try:
        with target_engine.connect() as connection:
            locked = connection.execute(
                text("SELECT GET_LOCK(:name, 30)"), {"name": LOCK_NAME}
            ).scalar()
            if locked != 1:
                raise RuntimeError("Could not acquire the database migration lock.")

            try:
                config = Config(str(BACKEND_DIR / "alembic.ini"))
                config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
                config.set_main_option(
                    "sqlalchemy.url", migrate_url.replace("%", "%%")
                )
                command.upgrade(config, "head")
                logger.info("Database migrations applied.")
            finally:
                connection.execute(
                    text("SELECT RELEASE_LOCK(:name)"), {"name": LOCK_NAME}
                )
    finally:
        if using_dedicated_engine:
            target_engine.dispose()
