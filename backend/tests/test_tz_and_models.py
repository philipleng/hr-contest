"""时区工具与 models/Alembic 结构同步单测"""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfoNotFoundError

import pytest
from sqlalchemy.dialects import mysql, sqlite
from sqlalchemy.schema import CreateTable

from app.config import settings
from app.models import (
    Applicant,
    CandidateSource,
    ResumeDocument,
)
from app.utils import tz as tz_mod


def test_app_timezone_config_defaults():
    assert settings.APP_TIMEZONE == "Asia/Manila"
    assert settings.app_timezone == "Asia/Manila"


def test_tz_fallback_without_tzdata(monkeypatch):
    """Windows 缺失 tzdata 时，ZoneInfo 抛异常仍可通过纯标准库回退解析。"""
    tz_mod.resolve_timezone.cache_clear()

    def _missing_zoneinfo(_name: str):
        raise ZoneInfoNotFoundError("No time zone found")

    monkeypatch.setattr(tz_mod, "ZoneInfo", _missing_zoneinfo)
    try:
        manila = tz_mod.resolve_timezone("Asia/Manila")
        assert manila.utcoffset(None) == timedelta(hours=8)

        shanghai = tz_mod.resolve_timezone("Asia/Shanghai")
        assert shanghai.utcoffset(None) == timedelta(hours=8)

        utc = tz_mod.resolve_timezone("UTC")
        assert utc == timezone.utc

        etc_utc = tz_mod.resolve_timezone("Etc/UTC")
        assert etc_utc == timezone.utc

        plus_offset = tz_mod.resolve_timezone("+08:00")
        assert plus_offset.utcoffset(None) == timedelta(hours=8)

        minus_offset = tz_mod.resolve_timezone("-05:30")
        assert minus_offset.utcoffset(None) == -timedelta(hours=5, minutes=30)

        with pytest.raises(ValueError):
            tz_mod.resolve_timezone("Mars/Olympus")
    finally:
        tz_mod.resolve_timezone.cache_clear()


def test_tz_now_today_and_half_open_day_range():
    local_now = tz_mod.now_local()
    assert local_now.tzinfo is None
    assert tz_mod.today_local() == local_now.date()

    start, end = tz_mod.day_range(date(2026, 2, 28))
    assert start == datetime(2026, 2, 28, 0, 0, 0)
    assert end == datetime(2026, 3, 1, 0, 0, 0)
    assert tz_mod.day_start(date(2026, 2, 28)) == start
    assert tz_mod.next_day_start(date(2026, 2, 28)) == end


def test_models_sync_indexes_and_mysql_variants():
    """校验 models.py 索引、可空性、MySQL 方言变体及 Python 时区默认值。"""
    applicant_indexes = {
        idx.name: [col.name for col in idx.columns]
        for idx in Applicant.__table__.indexes
    }
    assert applicant_indexes["idx_phone_normalized"] == ["phone_normalized"]
    assert applicant_indexes["idx_status_created"] == ["status", "created_at"]

    # 硬约束：gender 可空，phone 无 UNIQUE
    assert Applicant.__table__.c.gender.nullable is True
    assert not any(
        idx.unique and [c.name for c in idx.columns] == ["phone"]
        for idx in Applicant.__table__.indexes
    )
    assert Applicant.__table__.c.phone.unique is not True

    # 方言变体：MySQL 编译为 CHAR(64) / MEDIUMTEXT，SQLite 保持 VARCHAR / TEXT
    resume_mysql = str(CreateTable(ResumeDocument.__table__).compile(dialect=mysql.dialect()))
    resume_sqlite = str(CreateTable(ResumeDocument.__table__).compile(dialect=sqlite.dialect()))
    assert "CHAR(64) CHARACTER SET ascii COLLATE ascii_bin" in resume_mysql
    assert "MEDIUMTEXT" in resume_mysql
    assert "MEDIUMTEXT" not in resume_sqlite

    source_mysql = str(CreateTable(CandidateSource.__table__).compile(dialect=mysql.dialect()))
    source_sqlite = str(CreateTable(CandidateSource.__table__).compile(dialect=sqlite.dialect()))
    assert "MEDIUMTEXT" in source_mysql
    assert "MEDIUMTEXT" not in source_sqlite

    # Python 侧默认时间使用 now_local，避免 SQLite CURRENT_TIMESTAMP 返回 UTC 错位
    for col in (
        Applicant.__table__.c.created_at,
        Applicant.__table__.c.updated_at,
        CandidateSource.__table__.c.last_seen_at,
    ):
        assert getattr(col.default.arg, "__wrapped__", col.default.arg) is tz_mod.now_local
    for col in (
        Applicant.__table__.c.updated_at,
        CandidateSource.__table__.c.last_seen_at,
    ):
        assert getattr(col.onupdate.arg, "__wrapped__", col.onupdate.arg) is tz_mod.now_local
