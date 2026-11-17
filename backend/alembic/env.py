"""Alembic 运行环境：复用 app.config 的连接串与 app.models 的元数据。"""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings
from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# 若外部（如 migrate.py 或测试）尚未注入真实连接串，则从配置解析（优先 MIGRATE_DATABASE_URL）
configured_url = (config.get_main_option("sqlalchemy.url") or "").strip()
if not configured_url or configured_url.startswith("driver://"):
    # configparser 会把 % 当插值符，密码里的 % 必须转义
    config.set_main_option(
        "sqlalchemy.url",
        settings.resolve_migrate_database_url().replace("%", "%%"),
    )

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
