"""Alembic 基线迁移（0000..0007）与 MIGRATE_DATABASE_URL 单元测试"""

from __future__ import annotations

import importlib.util
import logging
import re
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory

import app.database as app_db
import app.migrate as migrate_mod
from app.config import Settings
from app.models import Applicant, ImportBatch, InterviewRecord, Staff, StatusHistory

BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
ALEMBIC_DIR = BACKEND_DIR / "alembic"
ENV_PY = ALEMBIC_DIR / "env.py"


def _load_migration_module(filename: str):
    path = ALEMBIC_DIR / "versions" / filename
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _extract_ddl_columns(sql: str) -> set[str]:
    """从 CREATE TABLE 语句提取列名（排除主键与索引定义行）。"""
    body = sql.split("(", 1)[1].rsplit(")", 1)[0]
    cols: set[str] = set()
    for raw_line in body.splitlines():
        line = raw_line.strip().rstrip(",")
        if not line:
            continue
        upper = line.upper()
        if upper.startswith(("PRIMARY KEY", "INDEX ", "KEY ", "UNIQUE ", "CONSTRAINT ")):
            continue
        if upper.startswith(("COMMENT '", "COMMENT=", "ON UPDATE", "ROW_FORMAT", "ENGINE")):
            continue
        col_name = line.split()[0].strip("`")
        cols.add(col_name)
    return cols


def test_alembic_linear_revision_chain():
    """ScriptDirectory 应有唯一 base '0000'、唯一 head '0007' 及完整线性链。"""
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_DIR))
    script = ScriptDirectory.from_config(cfg)

    assert script.get_bases() == ["0000"]
    assert script.get_heads() == ["0007"]

    revisions = [rev.revision for rev in reversed(list(script.walk_revisions()))]
    assert revisions == ["0000", "0001", "0002", "0003", "0005", "0007"]


def test_0000_core_tables_idempotent_and_mysql57_compliant(monkeypatch):
    """0000 应幂等建/删 5 张核心表，DDL 兼容 MySQL 5.7.32，并与 models.py 严格对齐。"""
    mod_0000 = _load_migration_module("0000_core_tables.py")
    mod_0003 = _load_migration_module("0003_applicant_patch.py")

    existing_tables: list[str] = []
    executed: list[str] = []

    fake_op = SimpleNamespace(
        get_bind=lambda: object(),
        execute=lambda sql: executed.append(str(sql)),
    )
    fake_inspector = SimpleNamespace(
        get_table_names=lambda: list(existing_tables),
        get_columns=lambda _t: [{"name": "updated_at"}],
        get_indexes=lambda _t: [],
    )
    monkeypatch.setattr(mod_0000, "op", fake_op)
    monkeypatch.setattr(mod_0000.sa, "inspect", lambda _bind: fake_inspector)

    # 1) 空库首次执行：创建全部 5 张核心表
    mod_0000.upgrade()
    assert len(executed) == 5

    table_ddls: dict[str, str] = {}
    for sql in executed:
        m = re.search(r"CREATE TABLE\s+(\w+)\s*\(", sql, flags=re.IGNORECASE)
        assert m is not None, sql
        table_ddls[m.group(1)] = sql

    assert set(table_ddls) == {
        "applicant",
        "staff",
        "status_history",
        "interview_record",
        "import_batch",
    }

    # 2) MySQL 5.7.32 合规与硬约束检查
    forbidden_patterns = (
        r"utf8mb4_0900_",
        r"\bJSON_TABLE\b",
        r"\bVALUES\s+ROW\b",
        r"\bRENAME\s+COLUMN\b",
        r"\bCHECK\s*\(",
        r"\bOVER\s*\(",
        r"\bWITH\s+\w+\s+AS\b",
        r"\bDESC\s*\)",
    )
    for name, ddl in table_ddls.items():
        assert "ENGINE=InnoDB" in ddl, name
        assert "DEFAULT CHARSET=utf8mb4" in ddl, name
        assert "COLLATE=utf8mb4_unicode_ci" in ddl, name
        for pattern in forbidden_patterns:
            assert not re.search(pattern, ddl, flags=re.IGNORECASE), f"{name}: {pattern}"

    applicant_ddl = table_ddls["applicant"]
    gender_line = next(
        line for line in applicant_ddl.splitlines() if line.strip().startswith("gender ")
    )
    assert "VARCHAR(16)" in gender_line
    assert "NOT NULL" not in gender_line

    phone_line = next(
        line for line in applicant_ddl.splitlines() if line.strip().startswith("phone ")
    )
    assert "UNIQUE" not in phone_line.upper()
    assert "INDEX idx_phone (phone)" in applicant_ddl
    assert not re.search(r"UNIQUE\s+(?:KEY|INDEX)?\s*\w*\s*\(\s*phone\s*\)", applicant_ddl, re.I)

    staff_ddl = table_ddls["staff"]
    assert re.search(r"username\s+VARCHAR\(64\)\s+NOT NULL\s+UNIQUE", staff_ddl)

    # 3) 表已存在时幂等跳过
    existing_tables.extend(table_ddls.keys())
    executed.clear()
    mod_0000.upgrade()
    assert executed == []

    # 4) downgrade 幂等删表与跳过
    executed.clear()
    mod_0000.downgrade()
    assert executed == [
        "DROP TABLE import_batch",
        "DROP TABLE interview_record",
        "DROP TABLE status_history",
        "DROP TABLE staff",
        "DROP TABLE applicant",
    ]
    existing_tables.clear()
    executed.clear()
    mod_0000.downgrade()
    assert executed == []

    # 5) 0000 + 0003 合并后的列集合与 models.py 完全一致
    cols_0000_applicant = _extract_ddl_columns(applicant_ddl)
    executed_0003: list[str] = []
    fake_bind_0003 = SimpleNamespace(
        execute=lambda *_args, **_kwargs: SimpleNamespace(scalar=lambda: 1)
    )
    monkeypatch.setattr(
        mod_0003,
        "op",
        SimpleNamespace(get_bind=lambda: fake_bind_0003, execute=lambda s: executed_0003.append(str(s))),
    )
    monkeypatch.setattr(
        mod_0003.sa,
        "inspect",
        lambda _bind: SimpleNamespace(
            get_columns=lambda _t: [{"name": c} for c in cols_0000_applicant],
            get_indexes=lambda _t: [],
        ),
    )
    mod_0003.upgrade()

    cols_0003_added = set()
    for stmt in executed_0003:
        m = re.search(r"ALTER TABLE applicant ADD COLUMN\s+(\w+)\s+", stmt)
        if m:
            cols_0003_added.add(m.group(1))

    assert cols_0003_added == {
        "phone_normalized",
        "availability",
        "available_from",
        "intent_tags",
        "merged_into_id",
    }
    assert cols_0000_applicant.isdisjoint(cols_0003_added)
    assert (cols_0000_applicant | cols_0003_added) == set(Applicant.__table__.columns.keys())

    assert _extract_ddl_columns(table_ddls["staff"]) == set(Staff.__table__.columns.keys())
    assert _extract_ddl_columns(table_ddls["status_history"]) == set(
        StatusHistory.__table__.columns.keys()
    )
    assert _extract_ddl_columns(table_ddls["interview_record"]) == set(
        InterviewRecord.__table__.columns.keys()
    )
    assert _extract_ddl_columns(table_ddls["import_batch"]) == set(
        ImportBatch.__table__.columns.keys()
    )


def test_resolve_migrate_database_url_priority_and_safe_warning(caplog):
    """独立 Settings 实例校验 MIGRATE_DATABASE_URL 优先级及空串回退告警脱敏。"""
    caplog.set_level(logging.WARNING, logger="app.config")

    dedicated = Settings(
        _env_file=None,
        DATABASE_URL="mysql+pymysql://hr_app:AppSecret99!@db:3306/hr_system",
        MIGRATE_DATABASE_URL="  mysql+pymysql://hr_migrate:MigSecret88!@db:3306/hr_system  ",
    )
    assert (
        dedicated.resolve_migrate_database_url()
        == "mysql+pymysql://hr_migrate:MigSecret88!@db:3306/hr_system"
    )
    assert caplog.records == []

    caplog.clear()
    fallback = Settings(
        _env_file=None,
        DATABASE_URL="mysql+pymysql://hr_app:AppSecret99!@db:3306/hr_system",
        MIGRATE_DATABASE_URL="   ",
    )
    resolved = fallback.resolve_migrate_database_url()
    assert resolved == "mysql+pymysql://hr_app:AppSecret99!@db:3306/hr_system"
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.WARNING
    assert "MIGRATE_DATABASE_URL" in caplog.text
    assert "AppSecret99!" not in caplog.text
    assert "mysql+pymysql://" not in caplog.text


class _FakeConn:
    def __init__(self, statements: list[str]):
        self.statements = statements

    def execute(self, stmt, _params=None):
        sql = str(stmt)
        self.statements.append(sql)
        return SimpleNamespace(scalar=lambda: 1)


class _FakeEngine:
    def __init__(self):
        self.statements: list[str] = []
        self.disposed = False

    @contextmanager
    def connect(self):
        yield _FakeConn(self.statements)

    def dispose(self):
        self.disposed = True


def test_migrate_uses_dedicated_engine_and_escapes_percent(monkeypatch):
    """配置 MIGRATE_DATABASE_URL 时应建临时 Engine、转义 % 并在 finally dispose。"""
    monkeypatch.setattr(migrate_mod.settings, "AUTO_MIGRATE", True)
    monkeypatch.setattr(
        migrate_mod.settings,
        "MIGRATE_DATABASE_URL",
        "sqlite+pysqlite:///dedicated%25mig.db",
    )

    created_urls: list[str] = []
    dedicated_engine = _FakeEngine()

    def fake_create_engine(url: str, **_kwargs):
        created_urls.append(url)
        return dedicated_engine

    captured_configs: list[Config] = []

    def fake_upgrade(cfg: Config, target: str):
        assert target == "head"
        captured_configs.append(cfg)

    monkeypatch.setattr(migrate_mod, "create_engine", fake_create_engine)
    monkeypatch.setattr(migrate_mod.command, "upgrade", fake_upgrade)

    migrate_mod.run_migrations()

    assert created_urls == ["sqlite+pysqlite:///dedicated%25mig.db"]
    assert dedicated_engine.disposed is True
    assert any("GET_LOCK" in s for s in dedicated_engine.statements)
    assert any("RELEASE_LOCK" in s for s in dedicated_engine.statements)
    assert len(captured_configs) == 1
    cfg = captured_configs[0]
    assert cfg.get_main_option("sqlalchemy.url") == "sqlite+pysqlite:///dedicated%25mig.db"
    assert (
        cfg.file_config.get("alembic", "sqlalchemy.url", raw=True)
        == "sqlite+pysqlite:///dedicated%%25mig.db"
    )


def test_migrate_and_env_cooperation_no_duplicate_warning_or_override(monkeypatch, caplog):
    """migrate.py 已注入真实连接串时，env.py 不应覆写也不应重复打印 warning；CLI 占位符时应解析。"""
    caplog.set_level(logging.WARNING, logger="app.config")

    # 场景 1：migrate.py 未配置 MIGRATE_DATABASE_URL，回退主引擎，仅打 1 条 warning
    fallback_engine = _FakeEngine()
    monkeypatch.setattr(app_db, "engine", fallback_engine)
    monkeypatch.setattr(migrate_mod.settings, "AUTO_MIGRATE", True)
    monkeypatch.setattr(migrate_mod.settings, "MIGRATE_DATABASE_URL", "")
    monkeypatch.setattr(
        migrate_mod.settings,
        "DATABASE_URL",
        "sqlite+pysqlite:///primary%25app.db",
    )

    def run_env_with_config(cfg: Config) -> None:
        mock_context = MagicMock()
        mock_context.config = cfg
        mock_context.is_offline_mode.return_value = True
        mock_context.begin_transaction.return_value = contextmanager(lambda: (yield))()

        monkeypatch.setattr("alembic.context.config", cfg, raising=False)
        env_globals = {
            "__file__": str(ENV_PY),
            "__name__": "alembic_env_test",
        }
        source = ENV_PY.read_text(encoding="utf-8").replace(
            "from alembic import context",
            "context = _test_context",
        )
        env_globals["_test_context"] = mock_context
        exec(compile(source, str(ENV_PY), "exec"), env_globals)

    monkeypatch.setattr(
        migrate_mod.command,
        "upgrade",
        lambda cfg, _target: run_env_with_config(cfg),
    )

    caplog.clear()
    migrate_mod.run_migrations()

    assert fallback_engine.disposed is False
    assert len(caplog.records) == 1

    # 场景 2：migrate.py 已配置 MIGRATE_DATABASE_URL，env.py 保留不覆写
    monkeypatch.setattr(
        migrate_mod.settings,
        "MIGRATE_DATABASE_URL",
        "sqlite+pysqlite:///env_should_not_override.db",
    )
    pre_cfg = Config(str(ALEMBIC_INI))
    pre_cfg.set_main_option("sqlalchemy.url", "sqlite+pysqlite:///from%25migrate.db".replace("%", "%%"))
    run_env_with_config(pre_cfg)
    assert pre_cfg.get_main_option("sqlalchemy.url") == "sqlite+pysqlite:///from%25migrate.db"

    # 场景 3：CLI 直接执行 alembic.ini（占位符 driver://...），env.py 解析 MIGRATE_DATABASE_URL 并转义 %
    cli_cfg = Config(str(ALEMBIC_INI))
    monkeypatch.setattr(
        migrate_mod.settings,
        "MIGRATE_DATABASE_URL",
        "sqlite+pysqlite:///cli%25mig.db",
    )
    run_env_with_config(cli_cfg)
    assert cli_cfg.get_main_option("sqlalchemy.url") == "sqlite+pysqlite:///cli%25mig.db"
    assert (
        cli_cfg.file_config.get("alembic", "sqlalchemy.url", raw=True)
        == "sqlite+pysqlite:///cli%%25mig.db"
    )
    # 恢复 sa.inspect 状态（sanity check）
    assert hasattr(sa, "inspect")
